"""Real browser + the complete pipeline, with deterministic model responses."""
import json
from types import SimpleNamespace

import pytest

from alienqa.llm import LLMConfig, Role, RoleConfig
from alienqa.loader import ProjectLoader
from alienqa.pipeline import AlienQAPipeline
from alienqa.review import Decision, ReportBuilder, ReviewState


def test_browser_issue_to_reviewed_self_contained_report(monkeypatch, http_base_url, tmp_path):
    expected = "点击后应有明确反馈"
    calls = []

    def completion(**kwargs):
        role = kwargs["model"].split("/")[-1]
        content = kwargs["messages"][0]["content"]
        prompt = content[0]["text"] if isinstance(content, list) else content
        calls.append((role, prompt))
        if role == "gist":
            text = json.dumps({"areas": [], "relations": []}) if "产品地图" in prompt else "一个交互演示页面。"
        elif role == "expectation":
            text = json.dumps({"expectations": [{"text": expected, "expectation_basis": {
                "type": "interaction_convention", "reference": "交互操作应说明结果"}}]})
        elif role == "visual":
            text = json.dumps({"changes": ["no_change"], "summary": "没有可见反馈"})
        elif role == "judge":
            text = json.dumps({"status": "mismatch", "mismatches": [{
                "expectation_id": "EX-ST-00001-001",
                "expectation": expected, "observation": "点击后没有反馈", "level": "medium",
                "reasoning": "用户需要知道点击是否生效",
            }]})
        elif role == "investigator":
            text = json.dumps({"root_cause_hypothesis": "需进一步确认反馈逻辑", "reproduction_steps": [],
                               "technical_evidence": {}, "affected_components": []})
        else:
            text = "<p>模型补充摘要</p>"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=None)

    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: SimpleNamespace(completion=completion))
    cfg = LLMConfig(roles={role.value: RoleConfig(model=f"test/{role.value}") for role in Role})
    pipeline = AlienQAPipeline(cfg, samples=1, max_actions=1, browser="chromium",
                               artifacts_dir=tmp_path, verbose=False)
    result = pipeline.collect(ProjectLoader().load_browser(f"{http_base_url}/demo-app/index.html"))
    assert not result.incomplete
    assert result.steps[0]["status"] == "mismatch"
    assert len(result.evidences) == 1 and len(result.issues) == 1
    ev = result.evidences[0]
    package = json.loads((tmp_path / "replay" / f"{ev.id}.json").read_text())
    assert package["issue_id"] == result.issues[0].id
    assert package["replay"]["url"].endswith("/demo-app/index.html")
    assert package["replay"]["action_sequence"] == []
    recorded = package["replay"]["target_action"]
    assert {key: recorded[key] for key in ("type", "target", "text")} == result.steps[0]["action"]
    assert recorded["step_id"] == result.steps[0]["step_id"]
    assert recorded["locator"] == result.steps[0]["execution"]["locator"]
    assert package["before_state_id"] == result.steps[0]["state_before"]
    assert package["after_state_id"] == result.steps[0]["state_after"]
    result.save(tmp_path)
    assert json.loads((tmp_path / "scan.json").read_text())["incomplete"] is False
    state = ReviewState()
    with pytest.raises(ValueError, match="尚未审核"):
        ReportBuilder(pipeline.client).build(result.evidences, state)
    state.decide(ev.id, Decision.CONFIRMED, "确认实际无反馈")
    report = ReportBuilder(pipeline.client).build(result.evidences, state, result.investigations)
    assert report.accepted_count == 1
    assert report.html.count("data:image/png;base64,") == 2
    assert expected in report.html
    expectation_prompt = next(prompt for role, prompt in calls if role == "expectation")
    assert "只会执行这一个动作" in expectation_prompt
    assert '"visible_history": []' in expectation_prompt
    assert "产品简介:" not in expectation_prompt


def test_pipeline_tracks_form_preparation_and_submits(monkeypatch, http_base_url, tmp_path):
    """The production loop must include field values in each observed state."""
    from alienqa.expectation import Expectation, JudgmentResult
    from alienqa.mapper import ProductMap
    from alienqa.observation.models import Observation

    class Expectations:
        def __init__(self, *args, **kwargs):
            pass

        def expect(self, ctx, info, action=None):
            return [Expectation("执行交互后应有可见反馈", expectation_basis={
                "type": "interaction_convention", "reference": "操作结果应可见"})]

        def evaluate(self, expectations, observation):
            return JudgmentResult("passed")

    class Observer:
        def __init__(self, *args):
            pass

        def observe_runtime(self, driver, before_runtime=None):
            from alienqa.observation import RuntimeObserver
            return RuntimeObserver().observe(driver, before_runtime)

        def observe_visual(self, before, after, action, driver, runtime):
            return Observation(before_image=before, after_image=after)

    monkeypatch.setattr("alienqa.pipeline.ProductMapper.map_from_browser", lambda *args: ProductMap())
    monkeypatch.setattr("alienqa.pipeline.ExpectationEngine", Expectations)
    monkeypatch.setattr("alienqa.pipeline.ObservationEngine", Observer)
    pipeline = AlienQAPipeline(LLMConfig(), max_actions=4, browser="chromium",
                               artifacts_dir=tmp_path, verbose=False)
    result = pipeline.collect(ProjectLoader().load_browser(f"{http_base_url}/form-app/index.html"))
    assert [step["action"]["type"] for step in result.steps] == ["type", "blur", "select", "click"]
    assert all(step["state_before"] != step["state_after"] for step in result.steps if step["action"]["type"] != "blur")
    assert result.steps[1]["trajectory"]["step_id"] == "ST-00002"
    assert result.states[-1].route.endswith("#submitted")
    assert not result.incomplete
