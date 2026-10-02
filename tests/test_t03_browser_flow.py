"""Real visible feedback, raw events and saved cognitive provenance; stub models."""
import json
from types import SimpleNamespace

import pytest

from alienqa.llm import LLMConfig, Role, RoleConfig
from alienqa.loader import ProjectLoader
from alienqa.mapper import ProductMap
from alienqa.pipeline import AlienQAPipeline
from alienqa.run_writer import load_snapshot


@pytest.mark.parametrize("variant,status", [("1", "passed"), ("2", "mismatch"), ("3", "passed"), ("4", "passed")])
@pytest.mark.parametrize("input_type", ["browser", "source"])
def test_visible_feedback_and_committed_history(monkeypatch, http_base_url, tmp_path, variant, status, input_type):
    calls = []
    expected = "保存后应有可见操作结果，按钮状态变化或合理校验提示均可"

    def completion(**kwargs):
        role = kwargs["model"].split("/")[-1]
        content = kwargs["messages"][0]["content"]
        prompt = content[0]["text"] if isinstance(content, list) else content
        calls.append((role, prompt))
        saved = load_snapshot(tmp_path)
        step = saved["steps"][-1] if saved["steps"] else None
        if role == "gist":
            # Only the locator may see the hidden scope instruction/map summary.
            assert "INTERNAL_SCOPE" in prompt
            text = '{"selectors":["#save","#next"],"keywords":[],"summary":"INTERNAL_SUMMARY"}'
        elif role == "expectation":
            assert saved["phase"] == "expectation"
            assert step["execution_status"] == "not_started"
            frozen = step["input"]["cognitive"]
            assert json.dumps(frozen, ensure_ascii=False) in prompt
            assert "INTERNAL_" not in prompt
            if step["index"] == 2:
                history = frozen["visible_history"]
                assert len(history) == 1 and history[0]["step_id"] == "ST-00001"
                assert "已保存" in history[0]["visible_result"]
                basis = {"type": "observed_behavior", "reference": "ST-00001: 已保存"}
            else:
                assert frozen["visible_history"] == []
                basis = {"type": "visible_copy", "reference": "保存"}
            text = json.dumps({"expectations": [{"text": expected, "expectation_basis": basis}]})
        elif role == "visual":
            assert step["execution_status"] == "completed" and step["raw_refs"]
            text = '{"changes":["other"],"summary":"原始文字记录可核对"}'
        elif role == "judge":
            assert "fixture action exception" not in prompt
            assert json.dumps(step["visible_result"], ensure_ascii=False) in prompt
            if variant == "2":
                assert step["visible_result"] == step["input"]["visible_text"]
            elif variant == "3":
                assert "请先填写邮箱" in step["visible_result"]
            else:
                assert "已保存" in step["visible_result"]
            exp = step["expectations"][0]
            assert exp["id"] in prompt
            rows = [{"expectation_id": exp["id"], "expectation": expected, "observation": "没有可见反馈",
                     "level": "medium", "reasoning": "点击后应说明操作结果"}] if status == "mismatch" else []
            text = json.dumps({"status": status, "mismatches": rows})
        else:
            text = '{"root_cause_hypothesis":"待核对","reproduction_steps":[],"technical_evidence":{},"affected_components":[]}'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=None)

    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: SimpleNamespace(completion=completion))
    monkeypatch.setattr("alienqa.pipeline.ProductMapper.map_from_browser", lambda *args: ProductMap(brief="INTERNAL_SOURCE_ANSWER"))
    monkeypatch.setattr("alienqa.pipeline.ProductMapper.map", lambda *args: ProductMap(brief="INTERNAL_SOURCE_ANSWER"))
    config = LLMConfig(roles={role.value: RoleConfig(model=f"test/{role.value}") for role in Role})
    pipeline = AlienQAPipeline(config, samples=2, max_actions=2 if variant == "4" else 1, browser="chromium",
                              unit="保存", instructions="INTERNAL_SCOPE", artifacts_dir=tmp_path, verbose=False)
    project = ProjectLoader().load_browser(f"{http_base_url}/cognition-app/index.html?variant={variant}")
    project.input_type = input_type
    result = pipeline.collect(project)
    assert not result.incomplete, result.steps
    assert all(s["status"] == status for s in result.steps)
    assert all(s["action"]["target"]["selector"] in {"#save", "#next"} for s in result.steps)
    saved = load_snapshot(tmp_path)
    assert len(saved["steps"][0]["expectation_generation"]["samples"]) == 2
    assert saved["steps"][0]["expectations"][0]["id"] == "EX-ST-00001-001"
    if variant == "2":
        assert {e.finding_kind for e in result.evidences} == {"technical_anomaly", "cognitive_mismatch"}
        cognitive = next(e for e in result.evidences if e.finding_kind == "cognitive_mismatch")
        assert cognitive.expectation_id == "EX-ST-00001-001"
        assert pipeline._evidence.store.get(cognitive.id).expectation_id == cognitive.expectation_id
    else:
        assert result.evidences == []


@pytest.mark.parametrize("response", ["not json", '{"expectations":[]}',
    '{"expectations":[{"text":"应反馈","expectation_basis":{"type":"observed_behavior","reference":"ST-00099: 已保存"}}]}'])
def test_invalid_or_empty_expectations_keep_real_technical_qa(monkeypatch, http_base_url, tmp_path, response):
    def completion(**kwargs):
        role = kwargs["model"].split("/")[-1]
        text = response if role == "expectation" else '{"root_cause_hypothesis":"待核对","reproduction_steps":[],"technical_evidence":{},"affected_components":[]}'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=None)

    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: SimpleNamespace(completion=completion))
    monkeypatch.setattr("alienqa.pipeline.ProductMapper.map_from_browser", lambda *args: ProductMap())
    config = LLMConfig(roles={role.value: RoleConfig(model=f"test/{role.value}") for role in Role})
    result = AlienQAPipeline(config, samples=1, max_actions=1, browser="chromium", artifacts_dir=tmp_path,
                             verbose=False).collect(ProjectLoader().load_browser(f"{http_base_url}/cognition-app/index.html?variant=2"))
    assert result.incomplete
    assert result.steps[0]["execution_status"] == "completed"
    assert result.steps[0]["cognitive_status"] == ("inconclusive" if response == '{"expectations":[]}' else "failed")
    assert len(result.evidences) == 1 and result.evidences[0].finding_kind == "technical_anomaly"
    assert load_snapshot(tmp_path)["steps"][0]["expectation_generation"]["samples"][0]["raw"] == response
