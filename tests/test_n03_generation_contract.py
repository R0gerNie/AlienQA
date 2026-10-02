"""Pre-action generation contracts motivated by the frozen T09 real batch."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from alienqa.cognitive_diagnostics import generation_view
from alienqa.driver import Action, Target
from alienqa.expectation import ExpectationEngine, PageInfo
from alienqa.expectation.contracts import _merge_samples_v2
from test_t03_cognition import Client, context, payload


def engine_for(responses):
    return ExpectationEngine(Client(responses), samples=len(responses))


def test_selected_enter_is_frozen_without_the_input_value_or_locator():
    engine = engine_for(['{"expectations":[]}'])
    expected = engine.expect(context(), PageInfo(),
        Action("press", Target(text="New Todo Input", selector="#PRIVATE"), "Enter"))
    assert not expected
    assert engine.last_input["action_parameters"] == {"key": "Enter"}
    assert '"key": "Enter"' in engine.client.prompts[0]
    assert "PRIVATE" not in engine.client.prompts[0]
    assert "Enter 等按键可以依据一般交互知识" in engine.client.prompts[0]


@pytest.mark.parametrize("kind,value,parameters", [
    ("type", "PASSWORD_SECRET", {}), ("select", "PRIVATE_OPTION", {}),
    ("press", "PASSWORD_SECRET", {"key": None}), ("press", "a", {"key": None}),
    ("press", "Tab", {"key": "Tab"}),
])
def test_action_parameter_allowlist_never_exposes_arbitrary_text(kind, value, parameters):
    engine = engine_for(['{"expectations":[]}'])
    engine.expect(context(), PageInfo(), Action(kind, Target(text="Input"), value))
    assert engine.last_input["action_parameters"] == parameters
    if value.startswith(("PASSWORD", "PRIVATE")):
        assert value not in engine.client.prompts[0]


@pytest.mark.parametrize("kind,text,template", [
    ("type", "在「New Todo Input」中输入文字后，输入框应可见地显示所输入的内容。", "input.visible_content"),
    ("blur", "New Todo Input 失去输入焦点，不再显示活动输入光标。", "input.blur_cursor"),
    ("click", "本次操作后应有可见结果反馈", "operation.visible_result"),
])
def test_action_scoped_optional_templates_preserve_original_basis(kind, text, template):
    response = payload("普通输入/失焦/反馈惯例", "interaction_convention", text)
    engine = engine_for([response, response])
    result = engine.expect(context(), PageInfo(), Action(kind, Target(text="New Todo Input")))
    assert [e.text for e in result] == [text]
    assert result[0].expectation_basis["reference"] == "普通输入/失焦/反馈惯例"
    assert engine.last_generation["expression_templates"][0]["id"] == template
    prompt = engine.client.prompts[0]
    assert text in prompt
    assert "仅规范表达，不构成必须产生预期的要求" in prompt
    assert "不能省略条件" in prompt
    assert result[0].prompt_version == "general-user-v4"


def test_conditional_blur_and_current_item_history_are_not_rewritten_into_templates():
    for kind, text in [
        ("blur", "New Todo Input 失去焦点，不再显示输入光标或聚焦样式（若有）。"),
        ("click", "点击后应有可见反馈，表明下一项的保存结果；不应仅凭点击前已有的「Saved」判断本次保存成功。"),
    ]:
        engine = engine_for([payload("惯例", "interaction_convention", text)])
        result = engine.expect(context(), PageInfo(), Action(kind, Target(text="New Todo Input")))
        assert result[0].text == text
        assert "历史仅是前序观察，不证明本次动作成功" in engine.client.prompts[0]


def test_empty_reason_survives_generation_and_the_shared_review_view():
    response = json.dumps({"expectations": [], "abstention": {
        "code": "insufficient_visible_basis", "reason": "界面没有承诺 Enter 的结果"}}, ensure_ascii=False)
    engine = engine_for([response, response])
    assert engine.expect(context(), PageInfo(), Action("press", Target(text="Input"), "Enter")) == []
    generation = engine.last_generation
    assert generation["coverage"] == "none"
    assert generation["coverage_reason"] == "no_expectations"
    assert generation["sampling"]["complete"]
    assert generation["samples"][0]["abstention"]["reason"] == "界面没有承诺 Enter 的结果"
    view = generation_view({"expectation_generation": generation})
    assert view["empty_samples"][0]["code"] == "insufficient_visible_basis"
    assert view["samples"][0]["abstention"] == generation["samples"][0]["abstention"]


def test_legacy_empty_reason_is_unrecorded_and_not_fabricated():
    engine = engine_for(['{"expectations":[]}'])
    assert engine.expect(context(), PageInfo(), Action("press", Target(text="Input"), "Enter")) == []
    assert engine.last_generation["empty_samples"] == [{"sample_index": 1, "code": "unrecorded", "reason": ""}]
    assert generation_view({})["coverage_reason"] == "unrecorded"


@pytest.mark.parametrize("abstention,nonempty", [
    ({"code": "insufficient_visible_basis", "reason": "x"}, True),
    ({"code": "unknown", "reason": "x"}, False),
    ({"code": "insufficient_visible_basis", "reason": ""}, False),
    ({"code": "insufficient_visible_basis", "reason": "x" * 501}, False),
    ({"code": "insufficient_visible_basis", "reason": "x", "extra": "hidden"}, False),
    ("no idea", False),
])
def test_invalid_or_contradictory_abstention_fails_and_keeps_raw_response(abstention, nonempty):
    response = json.dumps({"expectations": json.loads(payload())["expectations"] if nonempty else [],
                           "abstention": abstention})
    engine = engine_for([response])
    with pytest.raises(ValueError, match="abstention"):
        engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
    sample = engine.last_generation["samples"][0]
    assert sample["status"] == "failed" and sample["error_stage"] == "parse"
    assert sample["raw"] == response


def test_empty_sample_never_gains_support_or_becomes_a_vote_against_another_requirement():
    empty = json.dumps({"expectations": [], "abstention": {
        "code": "no_observable_expectation", "reason": "没有额外可观察要求"}})
    engine = engine_for([payload(), empty])
    assert len(engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))) == 1
    assert engine.last_generation["groups"][0]["support_count"] == 1
    assert len(engine.last_generation["empty_samples"]) == 1


def test_complete_sampling_union_over_five_is_fully_delivered():
    responses = [json.dumps({"expectations": [json.loads(payload(text=f"要求{i}"))["expectations"][0]
                                             for i in range(start, start+3)]}) for start in (0, 3)]
    engine = engine_for(responses)
    assert len(engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))) == 6
    assert engine.last_generation["sampling"]["complete"]
    assert engine.last_generation["coverage_reason"] == "expectations_accepted"


@pytest.mark.parametrize("case", json.loads((Path(__file__).parent / "fixtures/sampling-calibration/generation-contract-boundaries.json").read_text())["cases"], ids=lambda case: case["id"])
def test_saved_real_pairs_keep_conditions_and_empty_arrays(case):
    before = deepcopy(case["samples"])
    diagnostic = {}
    accepted, unresolved = _merge_samples_v2(case["samples"], action_desc=case["action"], diagnostics=diagnostic)
    assert len(accepted) == case["expected_accepted"]
    assert diagnostic["coverage"] == case["expected_coverage"]
    assert case["samples"] == before
    assert case["annotation"]["independent_review"] == "pending"
    if unresolved:
        assert {item["reason_code"] for item in unresolved} == {"relation_unknown"}
