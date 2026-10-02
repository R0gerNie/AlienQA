"""Recall takes priority; user opinions never certify engineering execution."""
import json

import pytest

from alienqa.acceptance import evidence_matrix, review_template, assess
from alienqa.cognitive_diagnostics import generation_view, step_incomplete
from alienqa.driver import Action, Target
from alienqa.expectation import ExpectationEngine, PageInfo
from alienqa.expectation.contracts import merge_samples
from test_sampling_calibration import row
from test_t03_cognition import Client, context, payload, bound_observation


@pytest.mark.parametrize("other", ["保存后不应出现可见反馈", "保存后必须出现 toast"])
def test_disagreement_keeps_each_candidate_and_nonblocking_relationships(other):
    samples = [[row("保存后应有可见反馈")], [row(other)]]
    diagnostic = {}
    accepted, unresolved = merge_samples(samples, action_desc="click 保存", diagnostics=diagnostic)
    assert sorted(accepted, key=lambda r: r["text"]) == sorted(sum(samples, []), key=lambda r: r["text"])
    assert not unresolved and diagnostic["coverage"] == "complete"
    assert diagnostic["relationship_warnings"]
    assert all(g["decision"] == "accepted" for g in diagnostic["groups"])
    view = generation_view({"expectation_generation": diagnostic})
    assert view["relationship_warnings"] == diagnostic["relationship_warnings"]


def test_combined_samples_can_check_more_than_five_without_discarding_any():
    responses = [json.dumps({"expectations": [row(f"要求{i}") for i in range(start, start+5)]})
                 for start in (0, 5)]
    engine = ExpectationEngine(Client(responses), samples=2)
    expectations = engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
    assert len(expectations) == 10 and len({e.id for e in expectations}) == 10
    assert {g["expectation_id"] for g in engine.last_generation["groups"]} == {e.id for e in expectations}


@pytest.mark.parametrize("failure", [ValueError("model timeout"), "not json"])
def test_failed_second_sample_does_not_veto_first_candidate(failure):
    class FailingClient(Client):
        def complete(self, *args):
            if isinstance(self.responses[0], Exception):
                raise self.responses.pop(0)
            return super().complete(*args)
    engine = ExpectationEngine(FailingClient([payload(), failure]), samples=2)
    expected = engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
    assert len(expected) == 1
    assert not engine.last_generation["sampling"]["complete"]
    assert engine.last_generation["samples"][1]["status"] == "failed"
    assert engine.last_generation["coverage_reason"] == "sampling_incomplete"


def test_general_interaction_knowledge_can_support_enter_without_product_training():
    engine = ExpectationEngine(Client([payload("输入后按 Enter 提交是常见交互", "interaction_convention",
                                              "按 Enter 后应创建待办")]), samples=1)
    assert engine.expect(context(), PageInfo(), Action("press", Target(text="New Todo Input"), "Enter"))
    prompt = engine.client.prompts[0]
    assert "可以使用你已有的一般交互知识" in prompt
    assert "相关行业知识" in prompt and "只有内部人才觉得理所当然" in prompt
    assert "Enter 不天然意味着提交或创建" not in prompt


def test_unverifiable_sibling_does_not_erase_a_reported_mismatch():
    engine = ExpectationEngine(Client([json.dumps({"expectations": [row("保存后应有可见反馈"), row("保存后应显示 toast")]})]), samples=1)
    expected = engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
    response = json.dumps({"status": "mismatch", "mismatches": [{
        "expectation_id": expected[0].id, "expectation": expected[0].text,
        "observation": "没有反馈", "level": "medium", "reasoning": "用户期待反馈"}],
        "unverifiable_expectation_ids": [expected[1].id], "error": "第二条被遮挡"})
    engine.roles.judge = lambda *a, **kw: response
    result = engine.evaluate(expected, bound_observation())
    assert result.status == "mismatch" and len(result.mismatches) == 1
    assert result.unverifiable_expectation_ids == [expected[1].id]
    assert step_incomplete({"status": "mismatch", "judgment_result": {
        "status": "mismatch", "unverifiable_expectation_ids": result.unverifiable_expectation_ids}})


def test_user_feedback_missing_or_disagreeing_never_blocks_engineering_release():
    records = [{"level": level, "status": "passed", "result": f"{level}.json", "models": "real"}
               for level in ("structure", "browser_mechanism", "installation", "real_model")]
    matrix = evidence_matrix(records)
    assert matrix["release_ready"]
    assert matrix["required_levels"] == ["structure", "browser_mechanism", "installation", "real_model"]
    assert evidence_matrix(records + [{"level": "independent_review", "status": "failed", "result": "opinion.json"}])["release_ready"]
    assert not evidence_matrix(records + [{"level": "installation", "status": "failed", "result": "broken.json"}])["release_ready"]


@pytest.mark.parametrize("unchecked,status,error", [
    (["UNKNOWN"], "mismatch", "遮挡"), (["EX-ST-00002-001"], "mismatch", "遮挡"),
    (["EX-ST-00002-002"] * 2, "mismatch", "遮挡"), (["EX-ST-00002-002"], "passed", "遮挡"),
    (["EX-ST-00002-002"], "mismatch", ""), ("EX-ST-00002-002", "mismatch", "遮挡"),
])
def test_partial_judgment_still_checks_identity_and_status(unchecked, status, error):
    engine = ExpectationEngine(Client([json.dumps({"expectations": [row("要求1"), row("要求2")]})]), samples=1)
    expected = engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
    response = json.dumps({"status": status, "mismatches": [] if status == "passed" else [{
        "expectation_id": expected[0].id, "expectation": expected[0].text,
        "observation": "未出现", "level": "medium", "reasoning": "用户预期"}],
        "unverifiable_expectation_ids": unchecked, "error": error})
    engine.roles.judge = lambda *a, **kw: response
    assert engine.evaluate(expected, bound_observation()).status == "failed"


def test_uncollected_optional_feedback_has_unknown_minutes_and_no_gate():
    rows = [{"id": "run", "status": "completed", "steps": []}]
    template = review_template(rows, [])
    result = assess(rows, [], template)
    assert template["required_for_acceptance"] is False
    assert result["required_for_acceptance"] is False
    assert result["review_minutes"] is None


def test_optional_opinion_does_not_change_platform_execution_status():
    records = [{"level": "browser_mechanism", "status": "passed", "result": "browser.xml", "platform": "macOS"},
               {"level": "independent_review", "status": "failed", "result": "opinion.json", "platform": "macOS"}]
    assert evidence_matrix(records)["platforms"]["macOS"] == "passed"
