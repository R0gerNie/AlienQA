import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from alienqa.driver import Action, Target
from alienqa.driver.runtime import RuntimeSignals
from alienqa.expectation import Expectation, ExpectationMismatch, JudgmentResult
from alienqa.llm import LLMConfig
from alienqa.loader import Project
from alienqa.mapper import ProductMap
from alienqa.observation.models import VisualObservation
from alienqa.pipeline import AlienQAPipeline
from alienqa.run_writer import load_snapshot


class Interrupted(BaseException):
    pass


@pytest.fixture
def setup(monkeypatch, tmp_path):
    calls = SimpleNamespace(map_error=None, expect_error=None, visual_error=None, judge_error=None,
                            execute_error=None, launch_error=None, screenshot_error=False, entry_error=False, executed=0)

    class Driver:
        def __init__(self, **kwargs):
            self.signals = RuntimeSignals()

        def set_runtime_context(self, **kwargs):
            self.signals.run_id = kwargs["run_id"]

        def launch(self, *args, **kwargs):
            if calls.entry_error:
                self.signals.record("page_error", {"message": "entry failure"})
            if calls.launch_error:
                raise calls.launch_error

        def close(self):
            pass

        def url(self):
            return "https://app.test/"

        def visible_text(self):
            return "Save"

        def form_state(self):
            return []

        def interactive_elements(self):
            return [{"tag": "button", "text": "Save", "selector": "#save"}]

        def screenshot(self):
            if calls.screenshot_error:
                raise RuntimeError("screenshot unavailable")
            return b"image"

        def collect_runtime(self):
            return self.signals

        def snapshot_runtime(self):
            return deepcopy(self.signals)

        def execute(self, *args, **kwargs):
            calls.executed += 1
            self.signals.record("page_error", {"message": "action exception"})
            self.signals.record("http_response", {"url": "https://app.test/api", "status": 500,
                                                  "method": "POST", "resource_type": "fetch"})
            if calls.execute_error:
                raise calls.execute_error

        def replay_data(self):
            return {"url": "https://app.test/", "action_sequence": []}

    def map_page(*args):
        saved = load_snapshot(tmp_path)
        assert saved["phase"] == "entry"
        if calls.map_error:
            raise calls.map_error
        return ProductMap()

    class Expectations:
        def __init__(self, *args, **kwargs):
            pass

        def expect(self, *args, **kwargs):
            if calls.expect_error:
                raise calls.expect_error
            return [Expectation("Save feedback", expectation_basis={
                "type": "interaction_convention", "reference": "提交操作应说明结果"})]

        def evaluate(self, *args):
            if calls.judge_error:
                raise calls.judge_error
            return JudgmentResult("mismatch", [ExpectationMismatch("Save feedback", "no feedback", reasoning="r")])

    def visual(*args, **kwargs):
        saved = load_snapshot(tmp_path)
        assert len(saved["evidences"]) == (3 if calls.entry_error else 2)
        assert saved["steps"][0]["execution_status"] == "completed"
        if calls.visual_error:
            raise calls.visual_error
        return VisualObservation(summary="no feedback")

    monkeypatch.setattr("alienqa.pipeline.PlaywrightDriver", Driver)
    monkeypatch.setattr("alienqa.pipeline.ProductMapper.map", map_page)
    monkeypatch.setattr("alienqa.pipeline.ProductMapper.map_from_browser", map_page)
    monkeypatch.setattr("alienqa.pipeline.ExpectationEngine", Expectations)
    monkeypatch.setattr("alienqa.observation.VisualObserver.observe", visual)
    monkeypatch.setattr("alienqa.pipeline.InvestigationAgent.investigate_issue", lambda *args: (_ for _ in ()).throw(RuntimeError("investigation unavailable")))
    pipeline = AlienQAPipeline(LLMConfig(), max_actions=1, artifacts_dir=tmp_path, verbose=False)
    return pipeline, calls, tmp_path


@pytest.mark.parametrize("input_type", ["browser", "source"])
def test_entry_evidence_is_saved_before_mapper_can_block(setup, input_type):
    pipeline, calls, directory = setup
    calls.entry_error = True
    calls.map_error = Interrupted()
    with pytest.raises(Interrupted):
        pipeline.collect(Project(input_type=input_type))
    saved = load_snapshot(directory)
    assert saved["evidences"][0]["finding_kind"] == "technical_anomaly"
    assert saved["evidences"][0]["action"] == {}


def test_action_evidence_survives_visual_interruption(setup):
    pipeline, calls, directory = setup
    calls.visual_error = Interrupted()
    with pytest.raises(Interrupted):
        pipeline.collect(Project())
    saved = load_snapshot(directory)
    assert len(saved["evidences"]) == 2
    assert saved["steps"][0]["cognitive_status"] == "pending"
    assert all(e["source_record_ids"] for e in saved["evidences"])


@pytest.mark.parametrize("entry_error", [True, False])
def test_launch_failure_preserves_entry_records_without_fabricating_findings(setup, entry_error):
    pipeline, calls, directory = setup
    calls.entry_error = entry_error
    calls.launch_error = RuntimeError("navigation failed")
    result = pipeline.collect(Project())
    saved = load_snapshot(directory)
    assert calls.executed == 0
    assert result.stop_reason == "error"
    assert result.incomplete
    assert saved["raw_refs"]
    assert len(saved["evidences"]) == int(entry_error)
    assert saved["diagnostics"][0]["stage"] == "launch"


@pytest.mark.parametrize("failure", ["map_error", "expect_error", "visual_error", "judge_error", "execute_error"])
def test_each_phase_failure_preserves_technical_evidence(setup, failure):
    pipeline, calls, directory = setup
    setattr(calls, failure, RuntimeError(failure))
    result = pipeline.collect(Project())
    assert calls.executed == 1
    assert result.incomplete
    assert len([e for e in result.evidences if e.finding_kind == "technical_anomaly"]) == 2
    assert load_snapshot(directory)["evidences"]


def test_missing_screenshots_do_not_prevent_technical_execution(setup):
    pipeline, calls, directory = setup
    calls.screenshot_error = True
    result = pipeline.collect(Project())
    assert calls.executed == 1
    assert len(result.evidences) == 2
    assert result.incomplete
    assert any(d["stage"] == "artifact" for d in result.diagnostics)


def test_both_finding_kinds_and_basis_survive_issue_grouping(setup):
    pipeline, calls, directory = setup
    result = pipeline.collect(Project())
    saved = load_snapshot(directory)
    assert {e["finding_kind"] for e in saved["evidences"]} == {"technical_anomaly", "cognitive_mismatch"}
    cognitive = next(e for e in saved["evidences"] if e["finding_kind"] == "cognitive_mismatch")
    assert cognitive["expectation_basis"]["type"] == "interaction_convention"
    assert cognitive["step_id"] == saved["steps"][0]["step_id"]
    assert len({e["id"] for e in saved["evidences"]}) == 3
    assert {e.id for e in result.evidences} == {eid for issue in result.issues for eid in issue.evidence_ids}


def test_failed_grouping_does_not_commit_partial_member_mutations(setup, monkeypatch):
    pipeline, calls, directory = setup
    def broken_cluster(self, evidences):
        saved = load_snapshot(directory)
        assert {e.id for e in evidences} == {e['id'] for e in saved['evidences']}
        evidences[0].issue_id = 'HALF-GROUP'
        raise RuntimeError('grouping interrupted')
    monkeypatch.setattr('alienqa.pipeline.Deduplicator.cluster', broken_cluster)
    result = pipeline.collect(Project())
    saved = load_snapshot(directory)
    assert len(saved['evidences']) == 3
    assert all(not row['issue_id'] for row in saved['evidences'])
    assert result.issues == []
    assert any(d['stage'] == 'dedup' for d in saved['diagnostics'])


def test_mapper_failure_does_not_expand_unknown_scope(setup):
    pipeline, calls, directory = setup
    pipeline.unit = "settings"
    calls.entry_error = True
    calls.map_error = RuntimeError("mapper offline")
    result = pipeline.collect(Project())
    assert calls.executed == 0
    assert result.stop_reason == "scope_not_found"
    assert len(result.evidences) == 1


def test_sqlite_failure_is_storage_diagnostic_and_keeps_raw_prefix(setup, monkeypatch):
    import sqlite3
    from alienqa.run_writer import StorageError
    pipeline, calls, directory = setup
    def broken_insert(*args):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr("alienqa.evidence.storage.EvidenceStore.insert", broken_insert)
    with pytest.raises(StorageError, match="storage_failed"):
        pipeline.collect(Project())
    saved = load_snapshot(directory)
    assert saved["raw_refs"]
    assert saved["stop_reason"] == "storage_failed"
    assert saved["diagnostics"][-1]["stage"] == "storage"


def test_failed_action_retries_keep_action_identity_and_distinct_steps(setup):
    pipeline, calls, directory = setup
    pipeline.max_actions = 3
    calls.execute_error = RuntimeError("partially executed")
    result = pipeline.collect(Project())
    assert len(result.steps) == 2
    assert len({s["action_id"] for s in result.steps}) == 1
    assert len({s["step_id"] for s in result.steps}) == 2
    assert [s["attempt"] for s in result.steps] == [1, 2]
    assert all(s["execution_status"] == "failed" for s in result.steps)
