"""Cognitive contracts: visible inputs, grounded references and frozen identities."""
import json
from types import SimpleNamespace

import pytest

from alienqa.context import ExplorationContext, ExplorerContext, Observation as ContextObservation
from alienqa.driver import Action, Target
from alienqa.expectation import ExpectationEngine, PageInfo
from alienqa.mapper import ProductMap, Relation
from alienqa.observation.models import Observation, RuntimeObservation, VisualObservation


class Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def complete(self, role, messages):
        self.prompts.append(messages[0]["content"])
        return SimpleNamespace(text=self.responses.pop(0))

    def complete_vision(self, role, text, images):
        self.prompts.append(text)
        return SimpleNamespace(text=self.responses.pop(0))


def payload(reference="保存", kind="visible_copy", text="保存后应说明操作结果"):
    return json.dumps({"expectations": [{"text": text, "expectation_basis": {
        "type": kind, "reference": reference}}]}, ensure_ascii=False)


def context():
    return ExplorerContext(visible_text="保存", product_brief="INTERNAL_ANSWER",
                           run_id="run", step_id="ST-00002", action_id="A-00002")


def test_internal_map_does_not_change_visible_context():
    state = SimpleNamespace(id="S1", snapshot="保存", route="/app")
    builder = ExplorationContext()
    a = builder.build(ProductMap(brief="SECRET_A", relations=[Relation(from_="/app", to="/secret")]),
                      state, ContextObservation(visible_text="保存"), [])
    b = builder.build(ProductMap(brief="SECRET_B"), state, ContextObservation(visible_text="保存"), [])
    assert a.to_dict() == b.to_dict()
    assert "SECRET" not in json.dumps(a.to_dict())


def test_scope_and_direct_brief_are_not_expectation_inputs():
    client = Client([payload()])
    engine = ExpectationEngine(client, samples=1, focus="SECRET_SCOPE_INTERNAL_ANSWER")
    result = engine.expect(context(), PageInfo(elements=["按钮「保存」"]), Action("click", Target(text="保存")))
    assert "INTERNAL_ANSWER" not in client.prompts[0]
    assert "SECRET_SCOPE" not in client.prompts[0]
    assert result[0].step_id == "ST-00002"
    assert result[0].id == "EX-ST-00002-001"
    assert engine.last_generation["samples"][0]["raw"] == payload()


@pytest.mark.parametrize("kind,reference", [
    ("visible_copy", "不可见内部答案"), ("observed_behavior", "ST-00003: 已保存"),
    ("observed_behavior", "ST-00001: 编造观察"), ("interaction_convention", "x" * 501),
])
def test_unverifiable_or_unbounded_basis_fails(kind, reference):
    ctx = context()
    ctx.visible_history = [{"step_id": "ST-00001", "action": "click 保存", "visible_result": "已保存"}]
    client = Client([payload(reference, kind)])
    engine = ExpectationEngine(client, samples=1)
    with pytest.raises(ValueError):
        engine.expect(ctx, PageInfo(), Action("click", Target(text="保存")))
    assert engine.last_generation["samples"][0]["raw"]


def test_only_completed_visible_history_is_kept_and_bounded():
    steps = [{"step_id": f"ST-{i:05d}", "execution_status": "completed", "action": {
        "type": "type", "text": "PASSWORD_SECRET", "target": {"text": "输入"}},
        "visible_result": "已保存" + "x" * 1500, "technical": "HIDDEN_LOG", "reasoning": "INTERNAL"}
             for i in range(1, 8)]
    steps += [{"step_id": "ST-00008", "execution_status": "failed", "visible_result": "FAILED"}]
    ctx = ExplorationContext().build(None, None, ContextObservation(visible_text="保存"), steps)
    assert len(ctx.visible_history) == 5
    assert ctx.visible_history[0]["step_id"] == "ST-00003"
    assert all(len(row["visible_result"]) <= 1000 for row in ctx.visible_history)
    assert ctx.input_limits["history_truncated"]
    assert "PASSWORD_SECRET" not in json.dumps(ctx.to_dict())
    assert "HIDDEN_LOG" not in json.dumps(ctx.to_dict())


def test_observed_basis_must_quote_saved_step_result():
    ctx = context()
    ctx.visible_history = [{"step_id": "ST-00001", "action": "click 保存", "visible_result": "已保存"}]
    client = Client([payload("ST-00001: 已保存", "observed_behavior")])
    exp = ExpectationEngine(client, samples=1).expect(ctx, PageInfo(), Action("click", Target(text="保存")))
    assert exp[0].expectation_basis["reference"] == "ST-00001: 已保存"
    assert "ST-00001" in client.prompts[0]


def test_disagreeing_samples_are_unresolved_instead_of_union():
    client = Client([payload(text="打开弹窗"), payload(text="直接跳转")])
    engine = ExpectationEngine(client, samples=2)
    assert engine.expect(context(), PageInfo(), Action("click", Target(text="保存"))) == []
    assert engine.last_generation["unresolved"]
    assert len(engine.last_generation["samples"]) == 2


def test_expectation_count_limit_rejects_model_output():
    rows = [json.loads(payload(text=f"结果{i}"))["expectations"][0] for i in range(6)]
    engine = ExpectationEngine(Client([json.dumps({"expectations": rows})]), samples=1)
    with pytest.raises(ValueError):
        engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))


def bound_observation(step_id="ST-00002"):
    return Observation(before_image=b"before", after_image=b"after", action_desc="click 保存",
                       run_id="run", step_id=step_id, action_id="A-00002",
                       before_text="保存", after_text="已保存", visual=VisualObservation(summary="按钮变为已保存"),
                       runtime=RuntimeObservation(console_errors=["SECRET_LOG"]))


def test_same_action_label_on_another_step_cannot_reuse_expectations():
    engine = ExpectationEngine(Client([payload()]), samples=1)
    exp = engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
    result = engine.evaluate(exp, bound_observation("ST-00003"))
    assert result.status == "failed"
    assert len(engine.client.prompts) == 1


def test_judgment_uses_ids_basis_visible_facts_and_no_technical_logs():
    client = Client([payload(), '{"status":"passed","mismatches":[]}'])
    engine = ExpectationEngine(client, samples=1)
    exp = engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
    assert engine.evaluate(exp, bound_observation()).status == "passed"
    prompt = client.prompts[-1]
    assert "EX-ST-00002-001" in prompt and "visible_copy" in prompt
    assert "已保存" in prompt
    assert "SECRET_LOG" not in prompt


def test_judgment_cannot_change_text_or_expectation_identity():
    bad = json.dumps({"status": "mismatch", "mismatches": [{"expectation_id": "EX-FUTURE-001",
        "expectation": "保存后应说明操作结果", "observation": "无反馈", "level": "medium", "reasoning": "r"}]})
    engine = ExpectationEngine(Client([payload(), bad, bad]), samples=1)
    exp = engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
    assert engine.evaluate(exp, bound_observation()).status == "failed"


def test_absence_is_not_a_conflicting_requirement():
    engine = ExpectationEngine(Client([payload(), '{"expectations":[]}']), samples=2)
    assert len(engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))) == 1
    assert engine.last_generation["unresolved"] == []


def test_selector_and_typed_value_do_not_enter_model_prompt():
    client = Client([payload()])
    engine = ExpectationEngine(client, samples=1)
    engine.expect(context(), PageInfo(), Action("type", Target(selector="#INTERNAL_SELECTOR"), "PASSWORD_SECRET"))
    assert "INTERNAL_SELECTOR" not in client.prompts[0]
    assert "PASSWORD_SECRET" not in client.prompts[0]


def test_bound_expectation_with_invalid_basis_cannot_pass():
    engine = ExpectationEngine(Client([payload(), '{"status":"passed","mismatches":[]}']), samples=1)
    expected = engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
    expected[0].expectation_basis = None
    assert engine.evaluate(expected, bound_observation()).status == "failed"


def test_judgment_duplicate_reference_is_rejected_and_raw_is_retained():
    row = {"expectation_id": "EX-ST-00002-001", "expectation": "保存后应说明操作结果",
           "observation": "无反馈", "level": "medium", "reasoning": "r"}
    bad = json.dumps({"status": "mismatch", "mismatches": [row, row]})
    engine = ExpectationEngine(Client([payload(), bad, bad]), samples=1)
    expected = engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
    assert engine.evaluate(expected, bound_observation()).status == "failed"
    assert len(engine.last_judgment) == 2
    assert engine.last_judgment[0]["raw"] == bad


def test_history_does_not_include_failed_or_unobserved_actions():
    ctx = ExplorationContext().build(None, None, ContextObservation(visible_text="保存"), [
        {"step_id": "ST-00001", "execution_status": "failed", "action": {"type": "click", "target": {"text": "隐藏"}}}])
    assert ctx.action_history == [] and ctx.visible_history == []


def test_visual_model_cannot_receive_hidden_locator_label():
    from alienqa.observation import ObservationEngine
    client = Client(['{"changes":["no_change"],"summary":"无变化"}'])
    action = Action("click", Target(selector="#INTERNAL_SELECTOR"))
    observation = ObservationEngine(client).observe_visual(b"before", b"after", action,
                        SimpleNamespace(visible_text=lambda: "保存"), RuntimeObservation())
    assert observation.action_desc == "click #INTERNAL_SELECTOR"  # legacy display identity
    assert "INTERNAL_SELECTOR" not in client.prompts[0]


def test_frozen_input_records_each_truncation_boundary():
    ctx = context()
    ctx.visible_text = "x" * 5000
    ctx.visible_history = [{"step_id": "ST-00001", "action": "click 保存", "visible_result": "y" * 1100}]
    engine = ExpectationEngine(Client([]), samples=1)
    frozen = engine.prepare_input(ctx, PageInfo(route="/" + "r" * 2500, elements=["e" * 101] * 41))
    assert len(frozen["visible_text"]) == 4000
    assert len(frozen["elements"]) == 40
    assert len(frozen["route"]) == 2000
    assert all(frozen["input_limits"][key] for key in ["visible_text_truncated", "elements_truncated",
                                                    "element_text_truncated", "history_result_truncated", "route_truncated"])
