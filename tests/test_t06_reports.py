"""T06: decisions, report modes, committed data and local cache consistency."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from alienqa.evidence import Evidence
from alienqa.review import Decision, HumanReview, ReportBuilder, ReviewState, create_app
from alienqa.run_writer import RunWriter, StorageError
from test_ui_app import _make_app


@pytest.fixture
def builder():
    result = ReportBuilder(SimpleNamespace())
    result.roles.compose_report = lambda *args, **kwargs: '<script>window.PWN=1</script><p>模型补充</p>'
    return result


def test_analysis_keeps_five_states_notes_provenance_and_counts(builder, tmp_path):
    states = list(Decision)
    evidences = [Evidence(id=f"EV-{i}", issue_id="same", expectation=f"原声-{i}",
                          finding_kind="cognitive_mismatch", expectation_basis={"type": "visible_copy", "reference": "保存"})
                 for i in range(5)]
    state = ReviewState()
    for ev, decision in zip(evidences, states):
        state.decide(ev.id, decision, '<script>备注攻击</script>中文备注')
    report = builder.build(evidences, state, mode="analysis", scan_context={"status": "partial", "run_dir": str(tmp_path)})
    assert report.mode == "analysis" and report.displayed_count == 5
    assert report.accepted_count == 1 and report.total_count == 5
    for i in range(5):
        assert f"原声-{i}" in report.html
    for decision in states:
        assert decision.value in report.html
    assert "事前依据" in report.html and "visible_copy" in report.html
    assert "中文备注" in report.html and "&lt;script&gt;备注攻击" in report.html
    assert "<script>" not in report.html and "window.PWN" not in report.html
    with pytest.raises(ValueError):
        builder.build(evidences, state)
    with pytest.raises(ValueError):
        builder.build([], state, mode="bogus")


def test_relative_artifacts_missing_files_and_credentials(builder, tmp_path):
    (tmp_path / "shot.png").write_bytes(b"image")
    (tmp_path / "technical.json").write_text('{"records":[{"message":"runtime message"}]}')
    ev = Evidence(id="EV", finding_kind="technical_anomaly", artifacts={"before": "shot.png", "after": "absent.png", "technical": "technical.json"},
                  replay={"cookies": [{"value": "COOKIE_SECRET"}], "storage_state": "STATE_SECRET", "url": "https://example.test"})
    calls = []
    builder.roles.compose_report = lambda payload, **kwargs: calls.append(payload) or ""
    report = builder.build([ev], ReviewState(), mode="analysis", scan_context={"run_dir": str(tmp_path), "cookies": "CONTEXT_SECRET"})
    assert "data:image/png;base64," in report.html and "runtime message" in report.html
    assert "截图文件不可用" in report.html and "认知依据不适用" in report.html
    assert not any(secret in report.html + calls[0] for secret in ("COOKIE_SECRET", "STATE_SECRET", "CONTEXT_SECRET"))
    ev.artifacts["technical"] = "absent.json"
    assert "不可读取" in builder.build([ev], ReviewState(), mode="analysis", scan_context={"run_dir": str(tmp_path)}).html


@pytest.fixture(params=["main", "standalone"])
def rig(request, builder, tmp_path):
    evs = [Evidence(id="EV-1", expectation="原声一"), Evidence(id="EV-2", expectation="原声二")]
    if request.param == "main":
        app = _make_app(tmp_path)
        runs = app.config["runs"]
        rec = runs.create("test")
        runs.save_results(rec.id, evs, [])
        runs.finish(rec.id, "done")
        app.config["report_builder"] = builder
        return SimpleNamespace(app=app, base=f"/runs/{rec.id}", directory=rec.dir, state=lambda: runs.load_review(rec.id), runs=runs, rec=rec)
    review = HumanReview()
    app = create_app(review, builder, report_path=str(tmp_path / "report.html"), review_path=str(tmp_path / "review.json"),
                     scan_context={"status": "done", "run_dir": str(tmp_path)})
    app.config["evidences"] = evs
    return SimpleNamespace(app=app, base="", directory=tmp_path, state=lambda: review.state, review=review)


@pytest.mark.parametrize("payload", [[], None, {}, {"evidence_id": [], "decision": "confirmed"},
    {"evidence_id": "EV-1", "decision": "pending"}, {"evidence_id": "EV-1", "decision": "confirmed", "note": []}])
def test_shared_decision_validation(rig, payload):
    response = rig.app.test_client().post(rig.base + "/decide", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 400
    assert not (rig.directory / "review.json").exists()


def test_modes_four_decisions_notes_download_and_cache_invalidation(rig):
    client = rig.app.test_client()
    assert client.get(rig.base + "/report?mode=analysis").status_code == 200
    assert client.get(rig.base + "/report").status_code == 409
    assert client.get(rig.base + "/report?mode=bogus").status_code == 400
    for decision in ("by-design", "skipped", "confirmed", "rejected"):
        response = client.post(rig.base + "/decide", json={"evidence_id": "EV-1", "decision": decision, "note": "中文备注"})
        assert response.get_json() == {"ok": True, "evidence_id": "EV-1", "decision": decision, "note": "中文备注"}
        assert rig.state().note("EV-1") == "中文备注"
        assert not (rig.directory / "analysis.html").exists()
        html = client.get(rig.base + "/report?mode=analysis&download=1")
        assert html.status_code == 200 and "attachment" in html.headers["Content-Disposition"]
        assert "中文备注" in html.get_data(as_text=True) and "原声二" in html.get_data(as_text=True)
    client.post(rig.base + "/decide", json={"evidence_id": "EV-2", "decision": "rejected"})
    assert client.get(rig.base + "/report").status_code == 200
    assert client.get(rig.base + "/report?mode=analysis").status_code == 200
    assert (rig.directory / "report.html").exists() and (rig.directory / "analysis.html").exists()
    client.post(rig.base + "/decide", json={"evidence_id": "EV-1", "decision": "rejected", "note": "仅改备注"})
    assert not (rig.directory / "report.html").exists() and not (rig.directory / "analysis.html").exists()
    path = rig.base + "/review" if rig.base else "/"
    html = client.get(path).get_data(as_text=True)
    assert "<select" in html and "<textarea" in html and "仅改备注" in html


def test_save_failure_does_not_advance_state(rig, monkeypatch):
    if rig.base:
        monkeypatch.setattr(rig.runs, "_write_json", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    else:
        monkeypatch.setattr(HumanReview, "save", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    result = rig.app.test_client().post(rig.base + "/decide", json={"evidence_id": "EV-1", "decision": "confirmed"})
    assert result.status_code == 500 and "保存" in result.get_json()["error"]
    assert rig.state().decision("EV-1") == Decision.PENDING


def test_corrupt_review_is_not_empty(rig):
    (rig.directory / "review.json").write_text('{"EV-1":{"decision":"confirmed","note":[]}}')
    response = rig.app.test_client().get(rig.base + "/report?mode=analysis")
    assert response.status_code == 409 and "review.json" in response.get_data(as_text=True)


@pytest.mark.parametrize("status", ["running", "unknown", "cleanup_failed"])
def test_nonterminal_cannot_serve_existing_file(builder, tmp_path, status):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("test")
    if status != "running":
        runs.finish(rec.id, status)
    (rec.dir / "analysis.html").write_text("stale")
    response = app.test_client().get(f"/runs/{rec.id}/report?mode=analysis")
    assert response.status_code == 409 and "stale" not in response.get_data(as_text=True)
    standalone = create_app(HumanReview(), builder, scan_context={"status": status})
    assert standalone.test_client().get("/report?mode=analysis").status_code == 409


def test_snapshot_reads_canonical_once_and_rejects_corruption(tmp_path, monkeypatch):
    from alienqa.ui.runs import RunManager
    import alienqa.ui.runs as module
    runs = RunManager(tmp_path)
    rec = runs.create("test")
    RunWriter(rec.dir, rec.id).checkpoint(phase="terminal", steps=[], evidences=[Evidence(id="EV")], diagnostics=[])
    runs.finish(rec.id, "done")
    original = module.load_snapshot
    calls = []
    monkeypatch.setattr(module, "load_snapshot", lambda path: calls.append(path) or original(path))
    snapshot = runs.load_report_snapshot(rec.id)
    assert len(calls) == 1 and snapshot["evidences"][0].id == "EV"
    assert snapshot["scan_context"]["checkpoint_seq"] == 1
    (rec.dir / "scan.json").write_text("broken")
    with pytest.raises(StorageError):
        runs.load_report_snapshot(rec.id)


def test_generation_and_save_share_lock_without_late_cache(rig, builder):
    entered = threading.Event()
    release = threading.Event()
    original = builder.build
    def blocking(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    builder.build = blocking
    with ThreadPoolExecutor(2) as pool:
        generation = pool.submit(lambda: rig.app.test_client().get(rig.base + "/report?mode=analysis"))
        assert entered.wait(5)
        saving = pool.submit(lambda: rig.app.test_client().post(rig.base + "/decide", json={"evidence_id": "EV-1", "decision": "by-design", "note": "new"}))
        release.set()
        assert generation.result().status_code == 200
        assert saving.result().status_code == 200
    assert not (rig.directory / "analysis.html").exists()


@pytest.mark.parametrize("change", ["results", "diagnostics", "scope", "replay"])
def test_consumed_data_updates_invalidate_both_and_update_authority(tmp_path, change):
    from alienqa.ui.runs import RunManager
    from alienqa.run_writer import load_snapshot
    runs = RunManager(tmp_path)
    rec = runs.create("test")
    RunWriter(rec.dir, rec.id).checkpoint(phase="terminal", steps=[], evidences=[Evidence(id="EV")], diagnostics=[])
    runs.finish(rec.id, "done")
    for name in ("analysis.html", "report.html"):
        (rec.dir / name).write_text("old")
    if change == "results":
        runs.save_results(rec.id, [Evidence(id="EV", expectation="new")], [])
        assert load_snapshot(rec.dir)["evidences"][0]["expectation"] == "new"
    elif change == "diagnostics":
        runs.save_diagnostics(rec.id, [], [{"error": "new"}], True)
        assert load_snapshot(rec.dir)["diagnostics"][0]["error"] == "new"
    elif change == "scope":
        runs.save_scope(rec.id, SimpleNamespace(summary="new"))
        assert load_snapshot(rec.dir)["scope"]["summary"] == "new"
    else:
        runs.save_replay_result(rec.id, "EV", {"status": "reproduced"})
        assert runs.load_report_snapshot(rec.id)["scan_context"]["replay_results"]["EV"]["status"] == "reproduced"
    assert not (rec.dir / "analysis.html").exists() and not (rec.dir / "report.html").exists()


@pytest.mark.parametrize("status", ["done", "partial", "error", "timeout", "cancelled"])
def test_committed_empty_or_diagnostic_only_terminal_is_an_analysis(tmp_path, builder, status):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("test")
    RunWriter(rec.dir, rec.id).checkpoint(phase="terminal", steps=[], evidences=[],
                                        diagnostics=[] if status == "done" else [{"error": "已停止的诊断"}], stop_reason=status)
    runs.finish(rec.id, status)
    app.config["report_builder"] = builder
    response = app.test_client().get(f"/runs/{rec.id}/report?mode=analysis")
    assert response.status_code == 200 and "未记录发现" in response.get_data(as_text=True)
    assert "测试全部通过" not in response.get_data(as_text=True)
    if status != "done":
        assert "已停止的诊断" in response.get_data(as_text=True)


def test_corrupt_or_absent_scan_cannot_be_hidden_by_cached_html(tmp_path, builder):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("test")
    runs.finish(rec.id, "done")
    app.config["report_builder"] = builder
    (rec.dir / "analysis.html").write_text("stale")
    route = f"/runs/{rec.id}/report?mode=analysis"
    assert app.test_client().get(route).status_code == 409
    runs.save_results(rec.id, [], [])
    (rec.dir / "investigations.json").write_text("broken")
    assert app.test_client().get(route).status_code == 409


def test_lock_rechecks_status_before_generation(tmp_path, builder, monkeypatch):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("test")
    runs.save_results(rec.id, [], [])
    runs.finish(rec.id, "done")
    app.config["report_builder"] = builder
    class ChangedAtLock:
        def __enter__(self):
            metadata = rec.dir / "run.json"
            value = json.loads(metadata.read_text())
            value["status"] = "running"
            metadata.write_text(json.dumps(value))
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(runs, "lock", ChangedAtLock())
    assert app.test_client().get(f"/runs/{rec.id}/report?mode=analysis").status_code == 409
    assert not (rec.dir / "analysis.html").exists()


def test_cache_delete_failure_does_not_save_new_decision(rig, monkeypatch):
    from pathlib import Path
    path = rig.directory / "analysis.html"
    path.write_text("old")
    original = Path.unlink
    def fail(self, *args, **kwargs):
        if self == path:
            raise PermissionError("cache locked")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail)
    response = rig.app.test_client().post(rig.base + "/decide", json={"evidence_id": "EV-1", "decision": "confirmed"})
    assert response.status_code == 500 and rig.state().decision("EV-1") == Decision.PENDING


@pytest.mark.parametrize("name,content", [("diagnostics.json", "{}"), ("unit_scope.json", "[]"),
    ("evidences.json", '[{"id":"EV","artifacts":[]}]'), ("investigations.json", '[{"technical_evidence":[]}]')])
def test_present_invalid_schema_is_explicit_read_error(tmp_path, builder, name, content):
    app = _make_app(tmp_path)
    app.config["report_builder"] = builder
    runs = app.config["runs"]
    rec = runs.create("test")
    runs.save_results(rec.id, [Evidence(id="EV")], [])
    runs.finish(rec.id, "done")
    (rec.dir / name).write_text(content)
    response = app.test_client().get(f"/runs/{rec.id}/report?mode=analysis")
    assert response.status_code == 409 and "invalid" in response.get_data(as_text=True)


def test_report_write_failure_is_visible_and_no_partial_cache(rig, monkeypatch):
    import importlib
    module = importlib.import_module("alienqa.ui.app" if rig.base else "alienqa.review.webui")
    monkeypatch.setattr(module, "atomic_write_bytes", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    response = rig.app.test_client().get(rig.base + "/report?mode=analysis")
    assert response.status_code == 500 and "保存报告" in response.get_json()["error"]
    assert not (rig.directory / "analysis.html").exists()


@pytest.mark.parametrize("change", ["results", "replay", "scope"])
def test_generation_and_data_update_do_not_revive_old_report(tmp_path, builder, change):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("test")
    runs.save_results(rec.id, [Evidence(id="EV")], [])
    runs.finish(rec.id, "done")
    app.config["report_builder"] = builder
    entered, release = threading.Event(), threading.Event()
    original = builder.build
    def blocking(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    builder.build = blocking
    def update():
        if change == "results":
            runs.save_results(rec.id, [Evidence(id="EV", expectation="new")], [])
        elif change == "scope":
            runs.save_scope(rec.id, SimpleNamespace(summary="new"))
        else:
            runs.save_replay_result(rec.id, "EV", {"status": "reproduced"})
    with ThreadPoolExecutor(2) as pool:
        generating = pool.submit(lambda: app.test_client().get(f"/runs/{rec.id}/report?mode=analysis"))
        assert entered.wait(5)
        updating = pool.submit(update)
        release.set()
        assert generating.result().status_code == 200
        updating.result()
    assert not (rec.dir / "analysis.html").exists()
