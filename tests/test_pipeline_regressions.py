"""Regression coverage for the complete action → judgment → run-status contract."""
from types import SimpleNamespace

import pytest

from alienqa.driver import Action, Target
from alienqa.driver.runtime import RuntimeSignals
from alienqa.expectation import Expectation
from alienqa.observation import RuntimeObserver
from alienqa.llm import LLMConfig
from alienqa.loader import Project
from alienqa.mapper import ProductMap
from alienqa.observation.models import Observation
from alienqa.pipeline import AlienQAPipeline, PipelineResult


@pytest.fixture
def rig(monkeypatch, tmp_path):
    calls = SimpleNamespace(bound=[], evaluated=[], recorded=[], launches=[], closed=0)
    calls.judgment = SimpleNamespace(status="passed", mismatches=[], error="")
    calls.execute_error = None
    calls.expect_error = None
    calls.observe_error = None
    calls.execution = None
    calls.expect_delay = 0
    action = Action("click", Target(selector="#save"))

    class Driver:
        def __init__(self, **kwargs):
            self.count = 0

        def launch(self, url, storage_state=None):
            calls.launches.append((url, storage_state))

        def close(self):
            calls.closed += 1

        def url(self):
            return "http://app.test/"

        def visible_text(self):
            return f"Save {self.count}"

        def screenshot(self):
            return b"image"

        def snapshot_runtime(self):
            return RuntimeSignals()

        def collect_runtime(self):
            return RuntimeSignals()

        def execute(self, selected, **kwargs):
            if calls.execute_error:
                raise calls.execute_error
            self.count += 1
            return calls.execution

    class Planner:
        def __init__(self, *args, **kwargs):
            pass

        def extract_candidates(self, driver):
            return []

        def plan(self, ctx, candidates, graph):
            return action

        def record_result(self, selected, state_id, success):
            calls.recorded.append((selected, state_id, success))

    class Expectations:
        def __init__(self, *args, **kwargs):
            pass

        def expect(self, ctx, info, action=None):
            calls.bound.append(action)
            if calls.expect_delay:
                import time
                time.sleep(calls.expect_delay)
            if calls.expect_error:
                raise calls.expect_error
            return [Expectation("Save should give feedback", expectation_basis={
                "type": "interaction_convention", "reference": "操作应有反馈"})]

        def evaluate(self, expected, observation):
            calls.evaluated.append(observation)
            return calls.judgment

        def judge(self, *args):
            return []

    class Observer:
        def __init__(self, *args):
            pass

        def observe_runtime(self, driver, before_runtime=None):
            return RuntimeObserver().observe(driver, before_runtime)

        def observe_visual(self, before, after, selected, driver, runtime):
            if calls.observe_error:
                raise calls.observe_error
            return Observation(before_image=before, after_image=after, action_desc="click #save")

    monkeypatch.setattr("alienqa.pipeline.PlaywrightDriver", Driver)
    monkeypatch.setattr("alienqa.pipeline.ActionPlanner", Planner)
    monkeypatch.setattr("alienqa.pipeline.ExpectationEngine", Expectations)
    monkeypatch.setattr("alienqa.pipeline.ObservationEngine", Observer)
    monkeypatch.setattr("alienqa.pipeline.ProductMapper.map", lambda *args: ProductMap())
    pipeline = AlienQAPipeline(LLMConfig(), max_actions=1, artifacts_dir=tmp_path, verbose=False)
    return pipeline, calls, action


def test_action_is_bound_and_success_is_recorded(rig):
    pipeline, calls, action = rig
    result = pipeline.collect(Project())
    assert calls.bound == [action]
    assert len(calls.evaluated) == 1
    assert calls.recorded[0][0] == action and calls.recorded[0][2] is True
    assert result.steps[0]["status"] == "passed"
    assert not result.incomplete


@pytest.mark.parametrize("status", ["failed", "inconclusive"])
def test_judgment_failure_is_persisted_as_incomplete(rig, status):
    pipeline, calls, _ = rig
    calls.judgment = SimpleNamespace(status=status, mismatches=[], error="model unavailable")
    result = pipeline.collect(Project())
    assert result.incomplete
    assert result.steps[0]["status"] == status
    assert result.steps[0]["error"] == "model unavailable"


def test_failed_action_is_visible_and_not_marked_successful(rig):
    pipeline, calls, _ = rig
    calls.execute_error = RuntimeError("button covered")
    result = pipeline.collect(Project())
    assert result.incomplete
    assert result.steps[0]["status"] == "action_failed"
    assert calls.recorded[0][2] is False
    assert calls.closed == 1


def test_expectation_failure_keeps_technical_execution(rig):
    pipeline, calls, _ = rig
    calls.expect_error = RuntimeError("expectation provider failed")
    result = pipeline.collect(Project())
    assert result.incomplete
    assert "expectation provider failed" in result.steps[0]["error"]
    assert calls.recorded[0][2] is True
    assert not calls.evaluated


def test_observation_failure_is_visible_after_successful_action(rig):
    pipeline, calls, _ = rig
    calls.observe_error = RuntimeError("visual unavailable")
    result = pipeline.collect(Project())
    assert result.incomplete
    assert result.steps[0]["status"] == "observation_failed"
    assert calls.recorded[0][2] is True


def test_source_mode_applies_storage_state(rig):
    pipeline, calls, _ = rig
    pipeline.collect(Project(storage_state="session.json"))
    assert calls.launches == [("http://localhost:3000", "session.json")]


def test_pipeline_requires_explicit_auto_confirmation():
    pipeline = AlienQAPipeline(LLMConfig(), verbose=False)
    assert pipeline.auto_confirm is False


def test_result_component_diagnostics_prevent_clean_status():
    result = PipelineResult(diagnostics=[{"stage": "investigation", "error": "failed"}])
    assert result.incomplete


@pytest.mark.parametrize("wait_status", ["timeout", "failed"])
def test_t02_emitted_but_unsettled_is_not_judged_or_retried(rig, wait_status):
    pipeline, calls, _ = rig
    calls.execution = {"status": "completed", "emitted": True, "wait": {"status": wait_status}}
    result = pipeline.collect(Project())
    assert result.steps[0]["execution_status"] == "completed"
    assert result.steps[0]["cognitive_status"] == "inconclusive"
    assert calls.recorded[0][2] is True
    assert not calls.evaluated and result.incomplete
    assert result.steps[0]["execution"]["wait"]["status"] == wait_status


def test_t02_rejected_controlled_input_keeps_failed_attempt(rig):
    pipeline, calls, _ = rig
    calls.execution = {"status": "input_rejected", "emitted": True, "value_accepted": False, "wait": {"status": "settled"}}
    result = pipeline.collect(Project())
    assert result.steps[0]["execution_status"] == "failed"
    assert not calls.evaluated and calls.recorded[0][2] is False
    assert result.steps[0]["trajectory"]["status"] == "failed"


def test_t02_model_latency_cannot_trigger_action_after_deadline(rig):
    pipeline, calls, _ = rig
    pipeline.max_seconds = .01
    calls.expect_delay = .02
    result = pipeline.collect(Project())
    assert result.stop_reason == "time_budget"
    assert result.steps[0]["execution_status"] == "not_started"
    assert not calls.recorded and not calls.evaluated
