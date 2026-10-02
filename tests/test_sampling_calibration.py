"""N03 merge contracts; evaluator labels stay outside generation prompts."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from alienqa.expectation.contracts import merge_samples

CORPUS = Path(__file__).parent / "fixtures/sampling-calibration/first-samples.json"
TARGETED_CORPUS = CORPUS.with_name("targeted-v2-samples.json")


def row(text, reference="保存", kind="visible_copy"):
    return {"text": text, "expectation_basis": {"type": kind, "reference": reference}}


def merge(samples, action="click 保存"):
    diagnostic = {}
    accepted, unresolved = merge_samples(samples, action_desc=action, diagnostics=diagnostic)
    return accepted, unresolved, diagnostic


@pytest.mark.parametrize("case", json.loads(CORPUS.read_text())["cases"] + json.loads(TARGETED_CORPUS.read_text())["cases"],
                         ids=lambda case: case["source"] + ":" + case["id"])
def test_first_real_pairs_preserve_original_representatives_and_pending_review(case):
    before = deepcopy(case["samples"])
    accepted, unresolved, diagnostic = merge(case["samples"], case["action"])
    assert len(accepted) == case["expected_accepted"]
    assert diagnostic["coverage"] == case["expected_coverage"]
    assert diagnostic["merge_version"].startswith("sampling-merge-v2")
    assert case["annotation"]["independent_review"] == "pending"
    assert all(item in sum(case["samples"], []) for item in accepted)
    assert case["samples"] == before
    if accepted:
        assert not unresolved and diagnostic["groups"][0]["support_count"] == 2
    else:
        assert all(item["reason_code"] == "relation_unknown" for item in unresolved)


@pytest.mark.parametrize("samples", [1, 2, 3])
def test_identical_requirements_and_empty_samples_are_not_votes(samples):
    accepted, unresolved, diagnostic = merge([[row("保存后应说明操作结果")]] + [[]] * (samples - 1))
    assert len(accepted) == 1 and not unresolved
    assert diagnostic["groups"][0]["support_count"] == 1
    assert diagnostic["coverage"] == "complete"


def test_compatible_feedback_requirements_share_basis_without_forced_union():
    a, b = row("保存后应说明操作结果"), row("保存后反馈应清晰可读")
    accepted, unresolved, _ = merge([[a], [a, b]])
    assert accepted == sorted([a, b], key=lambda item: item["text"])
    assert not unresolved


def test_unknown_addition_does_not_remove_shared_requirement():
    a, b = row("保存后应说明操作结果"), row("打开陌生的业务面板")
    accepted, unresolved, diagnostic = merge([[a], [a, b]])
    assert accepted == [a]
    assert [item["texts"] for item in unresolved] == [[b["text"]]]
    assert diagnostic["coverage"] == "partial"


@pytest.mark.parametrize("samples", [
    [[row("保存后应有可见反馈"), row("保存后不应出现可见反馈")]],
    [[row("保存后应有可见反馈")], [row("保存后不应出现可见反馈")]],
    [[row("保存后应有可见反馈")], [row("保存后应有可见反馈"), row("保存后不应出现可见反馈")]],
])
def test_known_conflicts_block_both_sides_even_with_majority_or_single_sample(samples):
    accepted, unresolved, diagnostic = merge(samples)
    assert accepted == []
    assert {item["reason_code"] for item in unresolved} == {"conflict"}
    assert diagnostic["coverage"] == "none"


@pytest.mark.parametrize("strong", [
    "保存后必须出现 toast", "保存后必须变为已保存", "保存后应保证保存成功",
    "保存后应在 3 秒内说明操作结果", "保存后不应没有反馈", "保存后应说明操作结果且后台写入数据库",
    "保存后应说明另一个账户的操作结果", "保存后应说明操作结果，若账户标识不可用则跳转",
    "保存后应说明操作结果或自动扣费", "保存后应说明操作结果，但不允许失败",
    "点击保存后，界面应提供可查看的操作结果，说明保存成功。",
    "点击保存后，界面应提供可查看的操作结果，反馈形式不限，但必须显示 toast。",
])
def test_limits_conditions_negation_and_extra_clauses_are_not_stripped(strong):
    accepted, unresolved, _ = merge([[row("保存后应说明操作结果")], [row(strong)]])
    assert not accepted
    assert unresolved and {item["reason_code"] for item in unresolved} == {"relation_unknown"}


def test_other_control_cannot_be_equated_to_current_action():
    accepted, unresolved, _ = merge([[row("保存后应说明操作结果")], [row("删除后应说明操作结果")]])
    assert not accepted and unresolved


def test_other_action_cannot_inherit_save_specific_outcome_clauses():
    normal = row("删除后应说明操作结果")
    other_object = row("删除后，界面应提供可观察的操作结果反馈，让我能判断操作是否完成，或是否因当前状态无法保存")
    accepted, unresolved, _ = merge([[normal], [other_object]], action="click 删除")
    assert accepted == [] and unresolved


@pytest.mark.parametrize("basis", [("visible_copy", "保存"), ("interaction_convention", "操作应有结果反馈")])
def test_multiple_valid_bases_do_not_destroy_same_requirement(basis):
    a = row("保存后应说明操作结果")
    b = row(a["text"], basis[1], basis[0])
    accepted, unresolved, diagnostic = merge([[a], [b]])
    assert len(accepted) == 1 and not unresolved
    assert diagnostic["groups"][0]["support_count"] == 2
    assert len(diagnostic["groups"][0]["members"]) == 2


def test_cross_basis_paraphrase_requires_supported_relationship():
    samples = [[row("保存后应说明操作结果")], [row("保存后应有可见结果反馈", "惯例", "interaction_convention")]]
    assert len(merge(samples)[0]) == 1
    assert not merge(samples)[1]
    assert not merge([[row("打开弹窗")], [row("直接跳转", "惯例", "interaction_convention")]])[0]


def test_order_does_not_change_representatives_and_members_keep_source_indices():
    a, b = row("保存后应说明操作结果"), row("保存后应有可见结果反馈")
    samples = [[b, a], [a]]
    accepted, unresolved, diagnostic = merge(samples)
    assert accepted == merge(list(reversed([list(reversed(rows)) for rows in samples])))[0]
    assert not unresolved
    members = diagnostic["groups"][0]["members"]
    assert {(m["sample_index"], m["row_index"]) for m in members} == {(1, 1), (1, 2), (2, 1)}
    assert diagnostic["groups"][0]["support_count"] == 2


def test_empty_generation_has_no_check_coverage():
    accepted, unresolved, diagnostic = merge([[], []])
    assert accepted == unresolved == []
    assert diagnostic["coverage"] == "none"


def test_merged_limit_reports_all_candidates_without_silent_truncation():
    diagnostic = {}
    samples = [[row(f"要求{i}") for i in range(3)], [row(f"要求{i}") for i in range(3, 6)]]
    with pytest.raises(ValueError, match="5"):
        merge_samples(samples, action_desc="click 保存", diagnostics=diagnostic)
    assert diagnostic["error_code"] == "merged_limit_exceeded"
    assert len(diagnostic["groups"]) == 6


def test_direct_sample_limit_remains_bounded():
    with pytest.raises(ValueError, match="5"):
        merge([[row(str(i)) for i in range(6)]])


def test_generation_keeps_sampling_completeness_and_frozen_group_identity():
    from alienqa.expectation import ExpectationEngine, PageInfo
    from alienqa.driver import Action, Target
    from test_t03_cognition import Client, context, payload
    engine = ExpectationEngine(Client([payload(text="保存后应说明操作结果"), payload(text="保存后应有可见结果反馈")]), samples=2)
    expectations = engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
    generation = engine.last_generation
    assert generation["sampling"] == {"requested": 2, "returned": 2, "validated": 2, "complete": True}
    assert generation["coverage"] == "complete"
    assert generation["groups"][0]["expectation_id"] == expectations[0].id
    assert generation["prompt_version"] == "general-user-v2"


def test_generation_template_is_optional_and_does_not_rewrite_restrictive_claims():
    from alienqa.expectation import ExpectationEngine, PageInfo
    from alienqa.driver import Action, Target
    from test_t03_cognition import Client, context, payload
    client = Client([payload(text="保存后必须出现 toast")])
    engine = ExpectationEngine(client, samples=1)
    expected = engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
    prompt = client.prompts[0]
    assert "本次操作后应有可见结果反馈" in prompt
    assert "不要求每个动作都提出它" in prompt
    assert "不能省略条件" in prompt
    assert expected[0].text == "保存后必须出现 toast"
    assert expected[0].prompt_version == "general-user-v2"


@pytest.mark.parametrize("failure", [ValueError("model timeout"), "not json", '{"expectations":[]}'])
def test_sampling_failures_and_empty_arrays_have_distinct_accounting(failure):
    from types import SimpleNamespace
    from alienqa.expectation import ExpectationEngine, PageInfo
    from alienqa.driver import Action, Target
    from test_t03_cognition import context, payload
    class Client:
        responses = [payload(text="保存后应说明操作结果"), failure]
        def complete(self, *args):
            result = self.responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return SimpleNamespace(text=result)
    engine = ExpectationEngine(Client(), samples=2)
    saved = []
    engine.roles.on_generation = lambda data: saved.append(deepcopy(data))
    if isinstance(failure, Exception) or failure == "not json":
        with pytest.raises(ValueError):
            engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))
        assert not engine.last_generation["sampling"]["complete"]
        assert engine.last_generation["sampling"]["validated"] == 1
        assert engine.last_generation["coverage"] == "none"
        assert engine.last_generation["samples"][-1]["status"] == "failed"
    else:
        assert len(engine.expect(context(), PageInfo(), Action("click", Target(text="保存")))) == 1
        assert engine.last_generation["sampling"]["complete"]
        assert engine.last_generation["groups"][0]["support_count"] == 1
    assert saved[0]["sampling"]["validated"] == 0
    assert saved[-1]["sampling"] == engine.last_generation["sampling"]


def test_interruption_during_second_sample_preserves_incomplete_prefix():
    from alienqa.llm.roles import LlmRoles
    from types import SimpleNamespace
    class Client:
        count = 0
        def complete(self, *args):
            self.count += 1
            if self.count == 2:
                raise KeyboardInterrupt
            return SimpleNamespace(text=json.dumps({"expectations": [row("保存后应说明操作结果")]}))
    roles = LlmRoles(Client())
    with pytest.raises(KeyboardInterrupt):
        roles.generate_expectations("", "保存", samples=2, with_basis=True, action_desc="click 保存")
    assert roles.last_generation["sampling"] == {"requested": 2, "returned": 1, "validated": 1, "complete": False}
    assert roles.last_generation["samples"][-1]["status"] == "cancelled"


def test_offline_replay_versions_keep_source_and_annotation_separate(tmp_path):
    from alienqa.expectation.calibration import compare_corpus, main
    corpus = json.loads(CORPUS.read_text())
    before = deepcopy(corpus)
    result = compare_corpus(corpus)
    assert corpus == before
    assert result["summary"]["cases"] == 5
    assert result["summary"]["v1_accepted_cases"] == 0
    assert result["summary"]["v2_accepted_cases"] == 4
    assert result["summary"]["independent_review_pending"] == 5
    assert result["summary"]["expectation_ids_created"] == 0
    assert result["summary"]["model_invocations"] == 0
    output = tmp_path / "offline.json"
    assert main(["--corpus", str(CORPUS), "--output", str(output)]) == 0
    saved = json.loads(output.read_text())
    assert saved["cases"][2]["v2"]["coverage"] == "none"
    with pytest.raises(SystemExit):
        main(["--corpus", str(CORPUS), "--output", str(output)])


def test_offline_replay_does_not_reconstruct_from_truncated_raw():
    from alienqa.expectation.calibration import compare_corpus
    corpus = {"cases": [{"id": "missing-parsed", "action": "click 保存",
                          "samples": [{"raw": '{"expectations":', "raw_truncated": True}]}]}
    result = compare_corpus(corpus)
    assert result["cases"][0]["status"] == "input_failed"
    assert result["summary"]["input_failed"] == 1
