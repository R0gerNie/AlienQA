"""Actual request boundaries, parse outcomes, privacy and unknown accounting."""
import json
from types import SimpleNamespace

import pytest

from alienqa.llm import LLMClient, LLMConfig, LlmRoles, RoleConfig


def response(text="ok", usage=None, **fields):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=usage, **fields)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    from alienqa.llm.metering import MeteringSink, load_summary
    sink = MeteringSink(tmp_path, "RUN")
    config = LLMConfig(roles={role: RoleConfig(model="test/primary", fallbacks=["test/fallback"])
                             for role in ("gist", "expectation", "visual", "judge", "investigator", "reporter")})
    client = LLMClient(config, sink=sink)
    calls, behavior = [], []
    def complete(**kwargs):
        calls.append(kwargs)
        before = load_summary(tmp_path, "RUN")
        if not client.metering_errors and before["data_status"] == "available":
            assert before["counts"]["started"] == 1
        item = behavior.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: SimpleNamespace(completion=complete))
    return SimpleNamespace(client=client, sink=sink, calls=calls, behavior=behavior, directory=tmp_path,
                           summary=lambda: load_summary(tmp_path, "RUN"))


def test_fallback_started_before_request_and_final_success_keeps_failure(rig):
    rig.behavior[:] = [RuntimeError("rate limited"), response(usage={"prompt_tokens": 10, "completion_tokens": 3})]
    with rig.client.call_scope(step_id="ST", phase="expectation", input_ref="scan.json#steps/ST/input/cognitive"):
        result = rig.client.complete("expectation", [{"role": "user", "content": "visible input"}])
    assert result.call_id
    rows = rig.sink.read_calls()
    assert len(rows) == 1 and rows[0]["step_id"] == "ST"
    assert [a["status"] for a in rows[0]["attempts"]] == ["failed", "succeeded"]
    assert rows[0]["attempts"][1]["model"] == "test/fallback"
    summary = rig.summary()
    assert summary["logical_calls"] == 1 and summary["attempts"] == 2
    assert summary["counts"]["failed"] == 1 and summary["counts"]["succeeded"] == 1
    assert summary["tokens"]["prompt_tokens"]["known"] == 10
    assert summary["tokens"]["prompt_tokens"]["unknown_attempts"] == 1
    assert summary["unknown_cost_attempts"] == 2
    assert all(call["max_retries"] == 0 and call["num_retries"] == 0 for call in rig.calls)
    assert rows[0]["attempts"][0]["config"]["max_retries"] == 0


def test_all_failures_and_restart_never_become_zero_cost(rig):
    rig.behavior[:] = [TimeoutError("timeout"), RuntimeError("unavailable")]
    with pytest.raises(RuntimeError, match="全部失败"):
        rig.client.complete("judge", [])
    summary = rig.summary()
    assert summary["attempts"] == 2 and summary["unknown_cost_attempts"] == 2
    assert summary["known_costs"] == {}
    assert summary["calls_by_status"]["failed"] == 1


@pytest.mark.parametrize("usage", [None, {"prompt_tokens": 4}, SimpleNamespace(model_dump=lambda: {"prompt_tokens": 4})])
def test_usage_compatibility_missing_fields_unknown(rig, usage):
    rig.behavior.append(response(usage=usage))
    result = rig.client.complete("gist", [])
    assert result.usage == ({} if usage is None else {"prompt_tokens": 4})
    assert rig.summary()["tokens"]["completion_tokens"]["unknown_attempts"] == 1


def test_costs_keep_currencies_sources_and_zero_distinct_from_unknown(rig):
    for currency, amount in (("USD", "0.02"), ("CNY", "0")):
        rig.behavior.append(response(usage={"total_tokens": 4}, provider_cost={"amount": amount, "currency": currency, "source": "provider_response"}))
        rig.client.complete("gist", [])
    rig.behavior.append(response())
    rig.client.complete("gist", [])
    summary = rig.summary()
    assert summary["known_costs"]["USD"]["amount"] == "0.02"
    assert summary["known_costs"]["CNY"]["amount"] == "0"
    assert summary["unknown_cost_attempts"] == 1 and summary["hard_cost_limit"] is False
    assert set(summary["by_role"]) == {"gist"}
    assert summary["by_model"]["test/primary"]["attempts"] == 3


def test_invalid_response_success_is_separate_from_parse_or_local_failure(rig):
    rig.behavior[:] = [SimpleNamespace(choices=[], usage={"total_tokens": 7}), response("fallback")]
    assert rig.client.complete("gist", []).text == "fallback"
    attempts = rig.sink.read_calls()[0]["attempts"]
    assert attempts[0]["status"] == "succeeded" and attempts[0]["response_error"]
    assert rig.summary()["attempts"] == 2


def test_parse_failure_and_repair_are_two_calls_not_duplicate_requests(rig):
    from alienqa.expectation import ExpectationEngine, Expectation, Observation
    rig.behavior[:] = [response("not json"), response('{"status":"passed","mismatches":[]}')]
    result = ExpectationEngine(rig.client).evaluate([Expectation(text="feedback")], Observation(before_image=b"a", after_image=b"b"))
    assert result.status == "passed"
    rows = rig.sink.read_calls()
    assert len(rows) == 2 and sum(len(row["attempts"]) for row in rows) == 2
    assert rows[0]["parse_status"] == "failed" and rows[1]["parse_status"] == "succeeded"
    assert rows[1]["parent_call_id"] == rows[0]["call_id"]
    assert rows[1]["purpose"] == "judge_repair"


def test_missing_image_records_local_failure_without_supplier_attempt(rig):
    with pytest.raises(FileNotFoundError):
        rig.client.complete_vision("visual", "compare", [rig.directory / "missing.png"])
    assert rig.calls == [] and rig.summary()["attempts"] == 0
    assert rig.summary()["calls_by_status"]["local_failed"] == 1


def test_secrets_never_enter_public_accounting(rig, monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "PRIVATE_API_SENTINEL")
    rig.behavior[:] = [RuntimeError("Authorization: Bearer PRIVATE_API_SENTINEL cookies=COOKIE_SENTINEL"), response(usage={"token": "PRIVATE_API_SENTINEL"})]
    rig.client.complete("gist", [{"role": "user", "content": "PRIVATE_PROMPT_SENTINEL"}])
    public = json.dumps(rig.summary()) + json.dumps(rig.sink.read_calls())
    for secret in ("PRIVATE_API_SENTINEL", "COOKIE_SENTINEL", "PRIVATE_PROMPT_SENTINEL"):
        assert secret not in public
    assert rig.sink.read_calls()[0]["input_ref"]


def test_unfinished_request_after_termination_retains_unknown_outcome(rig):
    from alienqa.llm.metering import close_unfinished
    call = rig.sink.start_call("visual", {}, purpose="observe_visual")
    rig.sink.start_attempt(call, "test/primary", {})
    close_unfinished(rig.directory, "RUN", "cancelled")
    rows = rig.sink.read_calls()
    assert rows[0]["status"] == "unknown" and rows[0]["attempts"][0]["status"] == "unknown"
    assert rows[0]["termination"] == "cancelled"
    summary = rig.summary()
    assert summary["counts"]["unknown"] == 1 and summary["unknown_cost_attempts"] == 1
    assert summary["tokens"]["total_tokens"]["unknown_attempts"] == 1


def test_termination_closes_unwritten_attempt_without_replacing_successful_call(rig, monkeypatch):
    from alienqa.llm.metering import close_unfinished
    rig.behavior.append(response("returned"))
    monkeypatch.setattr(rig.sink, "finish_attempt", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    assert rig.client.complete("gist", []).text == "returned"
    assert rig.sink.read_calls()[0]["status"] == "succeeded"
    close_unfinished(rig.directory, "RUN", "done")
    row = rig.sink.read_calls()[0]
    assert row["status"] == "succeeded"
    assert row["attempts"][0]["status"] == "unknown"
    assert rig.summary()["data_status"] == "storage_failed"


def test_ledger_corruption_during_request_does_not_replace_supplier_response(rig, monkeypatch):
    def complete(**kwargs):
        path = next((rig.directory / "llm" / "calls").glob("*.json"))
        path.write_text('{}')
        return response("returned")
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: SimpleNamespace(completion=complete))
    assert rig.client.complete("gist", []).text == "returned"
    assert rig.client.metering_errors and rig.summary()["data_status"] == "corrupt"


def test_unreadable_ledger_is_explicit_and_does_not_throw(rig, monkeypatch):
    from alienqa.llm.metering import MeteringSink
    monkeypatch.setattr(MeteringSink, "read_calls", lambda self: (_ for _ in ()).throw(PermissionError("read denied")))
    summary = rig.summary()
    assert summary["data_status"] == "corrupt" and summary["complete"] is False


def test_metering_write_failure_does_not_retry_or_drop_success(rig, monkeypatch):
    import alienqa.llm.metering as module
    errors = []
    rig.client.on_metering_error = errors.append
    monkeypatch.setattr(module, "atomic_write_json", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    rig.behavior.append(response("real response"))
    assert rig.client.complete("gist", []).text == "real response"
    assert len(rig.calls) == 1 and errors and rig.client.metering_errors


def test_absent_legacy_and_corrupt_metering_are_explicit(tmp_path):
    from alienqa.llm.metering import load_summary
    assert load_summary(tmp_path, "RUN")["data_status"] == "absent"
    (tmp_path / "llm" / "calls").mkdir(parents=True)
    (tmp_path / "llm" / "calls" / "broken.json").write_text("broken")
    assert load_summary(tmp_path, "RUN")["data_status"] == "corrupt"


def test_report_accounts_for_optional_reporter_and_bad_metering_does_not_block(rig):
    from alienqa.evidence import Evidence
    from alienqa.review import ReportBuilder, ReviewState
    rig.behavior.append(response("<p>model summary</p>", usage={"total_tokens": 5}))
    builder = ReportBuilder(rig.client)
    context = {"run_dir": str(rig.directory), "run_id": "RUN", "status": "done"}
    report = builder.build([Evidence(id="EV", expectation="recorded")], ReviewState(), mode="analysis", scan_context=context)
    assert rig.summary()["by_role"]["reporter"]["attempts"] == 1
    assert "LLM 调用与用量" in report.html and "unknown_cost_attempts" in report.html
    assert rig.sink.read_calls()[0]["phase"] == "reporter"
    (rig.directory / "llm" / "calls" / "broken.json").write_text("broken")
    rig.behavior[:] = [RuntimeError("unavailable"), RuntimeError("unavailable")]
    report = builder.build([Evidence(id="EV", expectation="recorded")], ReviewState(), mode="analysis", scan_context=context)
    assert "recorded" in report.html and "corrupt" in report.html


def test_main_ui_usage_and_cancellation_keep_unknown(rig):
    from test_ui_app import _make_app
    from alienqa.ui.app import _complete_scan
    from alienqa.llm.metering import MeteringSink
    app = _make_app(rig.directory)
    runs = app.config["runs"]
    rec = runs.create("test")
    sink = MeteringSink(rec.dir, rec.id)
    call = sink.start_call("visual", {}, purpose="observe_visual")
    sink.start_attempt(call, "test/primary", {})
    _complete_scan(app, rec.id, "cancelled")
    usage = runs.load_usage(rec.id)
    assert usage["counts"]["unknown"] == 1
    html = app.test_client().get(f"/runs/{rec.id}").get_data(as_text=True)
    assert "LLM 调用与用量" in html and "unknown_cost_attempts" in html
    html = app.test_client().get(f"/runs/{rec.id}/report?mode=analysis").get_data(as_text=True)
    assert "unknown_cost_attempts" in html and "未记录发现" in html


def test_locked_litellm_transport_does_not_hide_retry_requests(tmp_path, monkeypatch):
    """A real adapter/SDK against a local fake endpoint, with no paid requests."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from alienqa.llm.metering import MeteringSink, load_summary

    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.setenv("LITELLM_TELEMETRY", "False")
    import litellm
    monkeypatch.setattr(litellm, "telemetry", False)
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(request["model"])
            failed = request["model"] == "gpt-4o-mini"
            payload = {"error": {"message": "local rate limit", "type": "rate_limit_error"}} if failed else {
                "id": "local-response", "object": "chat.completion", "created": 1, "model": request["model"],
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "local success"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}}
            body = json.dumps(payload).encode()
            self.send_response(429 if failed else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    sink = MeteringSink(tmp_path, "RUN")
    config = LLMConfig(roles={"gist": RoleConfig(model="openai/gpt-4o-mini", fallbacks=["openai/gpt-4o"])})
    client = LLMClient(config, sink=sink)
    sink.initialize(config)
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: SimpleNamespace(completion=lambda **kwargs:
        litellm.completion(**kwargs, api_base=f"http://127.0.0.1:{server.server_port}/v1", api_key="local-fake-key")))
    try:
        assert client.complete("gist", [{"role": "user", "content": "local test"}]).text == "local success"
        assert received == ["gpt-4o-mini", "gpt-4o"]
        usage = load_summary(tmp_path, "RUN")
        assert usage["attempts"] == 2 and usage["counts"]["failed"] == 1
        assert usage["tokens"]["total_tokens"] == {"known": 6, "unknown_attempts": 1}
        assert usage["unknown_cost_attempts"] == 2
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
