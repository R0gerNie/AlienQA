"""Evaluation denominators and budgets; the default suite never calls a model."""
import json

import pytest


def test_budget_stops_before_request_and_does_not_count_denials_as_attempts(tmp_path, monkeypatch):
    from alienqa.evaluation import InvocationBudget
    from alienqa.llm import LLMClient, LLMConfig, RoleConfig
    from alienqa.llm.metering import MeteringSink
    from types import SimpleNamespace
    requested = []
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: SimpleNamespace(completion=lambda **kwargs:
        requested.append(kwargs) or {"choices": [{"message": {"content": "response"}}]}))
    budget = InvocationBudget(1)
    sink = MeteringSink(tmp_path, "RUN")
    client = LLMClient(LLMConfig(roles={"gist": RoleConfig(model="test/main", fallbacks=["test/backup"])}), sink=sink)
    client.before_request = budget.reserve
    assert client.complete("gist", []).text == "response"
    with pytest.raises(RuntimeError, match="预算"):
        client.complete("gist", [])
    assert len(requested) == budget.used == 1
    rows = sink.read_calls()
    assert sum(len(row["attempts"]) for row in rows) == 1
    assert rows[-1]["status"] == "local_failed" and rows[-1]["local_errors"]


def test_assessment_preserves_failed_inconclusive_and_missing_runs():
    from alienqa.evaluation import summarize_records
    rows = [
        {"id": "a", "status": "completed", "steps": [{"status": "passed", "coverage": "complete",
         "sampling": {"complete": True}, "execution_status": "completed"}], "assessment": "pending"},
        {"id": "b", "status": "partial", "steps": [{"status": "inconclusive"}], "assessment": "pending"},
        {"id": "c", "status": "error", "steps": [], "assessment": "pending"},
        {"id": "d", "status": "not_started", "steps": [], "assessment": "pending"},
    ]
    result = summarize_records(rows)
    assert result["planned_runs"] == 4 and result["executed_runs"] == 3
    assert result["usable_cognitive_steps"] == 1 and result["inconclusive_steps"] == 1
    assert result["unreviewed_runs"] == 4 and result["n06_closed"] is False
    assert "accuracy" not in result


def test_partial_mismatch_and_local_passed_do_not_inflate_complete_checks():
    from alienqa.evaluation import summarize_records
    rows = [{"status": "partial", "max_actions": 3, "assessment": "pending", "steps": [
        {"status": "inconclusive", "execution_status": "completed", "coverage": "partial", "sampling": {"complete": True},
         "local_judgment_status": "passed", "accepted_groups": 1, "unresolved": 1, "unresolved_reasons": {"relation_unknown": 1}},
        {"status": "mismatch", "execution_status": "completed", "coverage": "partial", "sampling": {"complete": True},
         "local_judgment_status": "mismatch", "accepted_groups": 1, "unresolved": 1, "unresolved_reasons": {"conflict": 1}},
        {"status": "passed", "execution_status": "completed"},
    ]}, {"status": "not_started", "max_actions": 1, "steps": [], "assessment": "pending"}]
    result = summarize_records(rows)
    assert result["usable_cognitive_steps"] == 0
    assert result["local_usable_cognitive_steps"] == 2
    assert result["coverage_counts"] == {"partial": 2, "unrecorded": 1}
    assert result["unresolved_reason_counts"] == {"relation_unknown": 1, "conflict": 1}
    assert result["planned_actions"] == 4 and result["executed_actions"] == 3
    assert result["sampling_complete_steps"] == 2


def test_control_manifest_repeats_with_answers_outside_model_inputs():
    from alienqa.evaluation import control_cases
    cases = control_cases(2)
    assert len(cases) == 8 and len({case["id"] for case in cases}) == 8
    assert {case["variant"] for case in cases} == {1, 2, 3, 4}
    assert all(case["reference"] for case in cases)
    assert all(case["max_actions"] == (2 if case["variant"] == 4 else 1) for case in cases)


@pytest.mark.parametrize("variants,planned", [([], 4), (["--variants", "1", "2"], 2)])
def test_runner_records_all_cases_when_budget_expires(tmp_path, monkeypatch, variants, planned):
    import alienqa.evaluation as evaluation
    from alienqa.pipeline import PipelineResult

    class Pipeline:
        def __init__(self, *args, **kwargs):
            from alienqa.llm import LLMClient, LLMConfig
            self.client = LLMClient(LLMConfig())
            self.directory = kwargs["artifacts_dir"]

        def collect(self, project):
            self.client.before_request("test/model")
            result = PipelineResult(steps=[{"status": "inconclusive", "cognitive_status": "inconclusive"}])
            result.save(self.directory)
            return result

    monkeypatch.setattr(evaluation, "AlienQAPipeline", Pipeline)
    # Local fake project: do not start a server or a model in this unit test.
    monkeypatch.setattr(evaluation, "_serve", lambda directory: (None, "http://localhost:1"))
    code = evaluation.main(["--output", str(tmp_path), "--max-calls", "1", "--repeats", "1", *variants])
    assert code == 2
    saved = json.loads((tmp_path / "evaluation.json").read_text())
    assert len(saved["runs"]) == planned and saved["invocations_used"] == 1
    assert saved["runs"][0]["status"] == "partial"
    assert all(row["status"] == "not_started" for row in saved["runs"][1:])
    assert saved["summary"]["n06_closed"] is False


def test_cancelled_evaluation_keeps_prefix_and_unknown_request(tmp_path, monkeypatch):
    import alienqa.evaluation as evaluation
    from alienqa.run_writer import RunWriter, load_snapshot
    from alienqa.llm.metering import MeteringSink, load_summary

    class Pipeline:
        def __init__(self, *args, **kwargs):
            from types import SimpleNamespace
            self.client = SimpleNamespace()
            self.directory = kwargs["artifacts_dir"]

        def collect(self, project):
            writer = RunWriter(self.directory)
            writer.checkpoint(phase="visual", steps=[{"status": "inconclusive", "cognitive_status": "pending"}], evidences=[], diagnostics=[])
            sink = MeteringSink(self.directory, writer.run_id)
            call = sink.start_call("visual", {})
            sink.start_attempt(call, "codex/test", {})
            raise KeyboardInterrupt()

    monkeypatch.setattr(evaluation, "AlienQAPipeline", Pipeline)
    monkeypatch.setattr(evaluation, "_serve", lambda directory: (None, "http://localhost:1"))
    assert evaluation.main(["--output", str(tmp_path), "--max-calls", "1"]) == 130
    saved = json.loads((tmp_path / "evaluation.json").read_text())
    row = saved["runs"][0]
    assert row["status"] == "cancelled"
    run_dir = tmp_path / row["run_dir"]
    snapshot = load_snapshot(run_dir)
    assert snapshot["stop_reason"] == "cancelled" and snapshot["steps"]
    assert load_summary(run_dir, snapshot["run_id"])["counts"]["unknown"] == 1
