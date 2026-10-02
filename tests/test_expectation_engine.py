"""Expectation Engine 测试：预期生成、盲判、解耦、白名单、技术信号（mock LLM）。"""
from types import SimpleNamespace

import pytest

from alienqa.context import ExplorerContext
from alienqa.driver import Action, Target
from alienqa.expectation import (
    Expectation,
    ExpectationEngine,
    JudgmentError,
    MismatchLevel,
    Observation,
    PageInfo,
)
from alienqa.expectation.models import parse_mismatches
from alienqa.llm import LLMClient, LLMConfig, RoleConfig
from alienqa.observation import RuntimeObservation


class _FakeLiteLLM:
    """按队列返回文本/异常，并记录每次调用的 kwargs。"""

    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = []

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        item = self.texts.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=item))],
            model=kwargs["model"],
            usage=None,
        )


@pytest.fixture
def fake_litellm(monkeypatch):
    fake = _FakeLiteLLM([])
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: fake)
    return fake


@pytest.fixture
def engine(fake_litellm):
    cfg = LLMConfig(roles={
        "expectation": RoleConfig(model="gpt-4o-mini", temperature=0.8),
        "judge": RoleConfig(model="gpt-4o", temperature=0.2),
    })
    return ExpectationEngine(LLMClient(cfg), samples=2)


def _prompt(call):
    content = call["messages"][0]["content"]
    if isinstance(content, list):
        return content[0]["text"]
    return content


def _ctx(**kw):
    defaults = dict(product_brief="电商后台", visible_text="有个保存按钮")
    defaults.update(kw)
    return ExplorerContext(**defaults)


# ---- expect()：预期生成（不读 Observation） ----

def test_expect_uses_context_and_page_info(engine, fake_litellm):
    fake_litellm.texts.extend([
        "- 点保存应有提示\n- 页面状态应变化",
        "- 点保存应有提示",  # 第 2 次采样
    ])
    out = engine.expect(_ctx(), PageInfo(route="/orders", elements=["按钮「保存」"]))
    assert [e.text for e in out] == ["点保存应有提示", "页面状态应变化"]
    call = fake_litellm.calls[0]
    assert call["model"] == "gpt-4o-mini"
    assert call["temperature"] == 0.8
    prompt = _prompt(call)
    assert "电商后台" not in prompt
    assert "有个保存按钮" in prompt
    assert "按钮「保存」" in prompt
    assert "/orders" in prompt


def test_expect_samples_and_dedup(engine, fake_litellm):
    fake_litellm.texts.extend([
        "- 点保存应有提示\n- 页面状态应变化",
        "- 点保存应有提示\n- 缺少加载反馈",
    ])
    out = engine.expect(_ctx(), PageInfo())
    texts = [e.text for e in out]
    assert len(texts) == 3  # 采样 2 次去重后
    assert "点保存应有提示" in texts
    assert len(fake_litellm.calls) == 2


def test_expect_keeps_unit_instruction_out_of_cognition(fake_litellm):
    cfg = LLMConfig(roles={"expectation": RoleConfig(model="gpt-4o-mini", temperature=0.8)})
    engine = ExpectationEngine(LLMClient(cfg), samples=1,
                               focus="单元：登录表单\n指令：错误密码应有提示")
    fake_litellm.texts.append("- 错误密码应有提示")
    engine.expect(_ctx(), PageInfo())
    prompt = _prompt(fake_litellm.calls[0])
    assert "登录表单" not in prompt
    assert "错误密码应有提示" not in prompt


def test_expect_binds_only_the_selected_action(engine, fake_litellm):
    payload = '{"expectations":[{"text":"输入后应显示邮箱内容","expectation_basis":{"type":"interaction_convention","reference":"输入值可见"}}]}'
    fake_litellm.texts.extend([payload, payload])
    action = Action(type="type", target=Target(text="邮箱", selector="#email"), text="user@example.com")
    out = engine.expect(_ctx(), PageInfo(elements=["保存", "删除", "邮箱"]), action)
    prompt = _prompt(fake_litellm.calls[0])
    assert "type 邮箱" in prompt
    assert "user@example.com" not in prompt
    assert "仅针对本次动作" in prompt
    assert "其它未执行" in prompt
    assert out[0].action_desc == "type 邮箱"


# ---- judge()：盲判 ----

def test_judge_returns_mismatch(engine, fake_litellm):
    fake_litellm.texts.append(
        '{"mismatches": [{"expectation": "点保存应有提示", "observation": "无任何反馈",'
        ' "level": "high", "reasoning": "保存类操作应有成功提示"}]}'
    )
    obs = Observation(before_image=b"a", after_image=b"b", action_desc="click 保存")
    m = engine.judge([Expectation(text="点保存应有提示")], obs)
    assert len(m) == 1
    assert m[0].level == MismatchLevel.HIGH
    assert m[0].expectation == "点保存应有提示"
    assert m[0].observation == "无任何反馈"


def test_judge_returns_empty_when_matched(engine, fake_litellm):
    fake_litellm.texts.append('{"mismatches": []}')
    m = engine.judge([Expectation(text="x")], Observation(before_image=b"a", after_image=b"b"))
    assert m == []


def test_judge_drops_bug_field(engine, fake_litellm):
    fake_litellm.texts.append(
        '{"mismatches": [{"level": "low", "bug": "这就是个 bug",'
        ' "expectation": "x", "observation": "y", "reasoning": "r"}]}'
    )
    m = engine.judge([Expectation(text="x")], Observation(before_image=b"a", after_image=b"b"))
    assert len(m) == 1
    assert not hasattr(m[0], "bug")
    assert m[0].level == MismatchLevel.LOW


def test_judge_technical_signals_stay_out_of_prompt(engine, fake_litellm):
    fake_litellm.texts.append('{"mismatches": []}')
    obs = Observation(
        before_image=b"a", after_image=b"b", action_desc="click 保存",
        runtime=RuntimeObservation(console_errors=["TypeError: x"], network_failures=["GET /api -> 500"]),
    )
    engine.judge([Expectation(text="x")], obs)
    prompt = _prompt(fake_litellm.calls[0])
    assert "click 保存" in prompt
    assert "TypeError: x" not in prompt
    assert "GET /api -> 500" not in prompt


def test_judge_retries_on_bad_json(engine, fake_litellm):
    fake_litellm.texts.extend([
        "not json at all",
        '{"mismatches": [{"expectation": "x", "observation": "y",'
        ' "level": "medium", "reasoning": "r"}]}',
    ])
    m = engine.judge([Expectation(text="x")], Observation(before_image=b"a", after_image=b"b"))
    assert len(m) == 1
    assert m[0].level == MismatchLevel.MEDIUM
    assert len(fake_litellm.calls) == 2
    assert "不是合法 JSON" in _prompt(fake_litellm.calls[1])


def test_judge_raises_when_all_invalid(engine, fake_litellm):
    fake_litellm.texts.extend(["bad1", "bad2"])
    with pytest.raises(JudgmentError, match="判定输出"):
        engine.judge([Expectation(text="x")], Observation(before_image=b"a", after_image=b"b"))
    assert len(fake_litellm.calls) == 2


def test_judge_empty_expectations_no_call(engine, fake_litellm):
    with pytest.raises(JudgmentError, match="预期"):
        engine.judge([], Observation(before_image=b"a", after_image=b"b"))
    assert fake_litellm.calls == []


@pytest.mark.parametrize("raw", [
    "{}",
    '{"mismatches": null}',
    '{"mismatches": {}}',
    '{"mismatches": "none"}',
    '{"mismatches": [null]}',
    '{"mismatches": [{"expectation": "x", "observation": "y", "level": "unknown", "reasoning": "r"}]}',
    '{"mismatches": [{"expectation": "x", "level": "low", "reasoning": "r"}]}',
    '{"mismatches": [{"expectation": 3, "observation": "y", "level": "low", "reasoning": "r"}]}',
    '{"mismatches": [{"expectation": "x", "observation": " ", "level": "low", "reasoning": "r"}]}',
    '{"mismatches": [], "status": "mismatch"}',
    '{"mismatches": [], "status": "made_up"}',
])
def test_parse_mismatches_rejects_invalid_schema(raw):
    with pytest.raises(ValueError):
        parse_mismatches(raw)


def test_evaluate_distinguishes_pass_from_mismatch(engine, fake_litellm):
    fake_litellm.texts.extend([
        '{"mismatches": []}',
        '{"mismatches": [{"expectation": "x", "observation": "y", "level": "medium", "reasoning": "r"}]}',
    ])
    obs = Observation(before_image=b"a", after_image=b"b")
    assert engine.evaluate([Expectation(text="x")], obs).status == "passed"
    result = engine.evaluate([Expectation(text="x")], obs)
    assert result.status == "mismatch"
    assert len(result.mismatches) == 1
    assert result.error == ""


@pytest.mark.parametrize("expectations, observation, reason", [
    ([], Observation(before_image=b"a", after_image=b"b"), "预期"),
    ([Expectation(text="x")], None, "观察"),
    ([Expectation(text="x")], Observation(after_image=b"b"), "截图"),
    ([Expectation(text="x")], Observation(before_image=b"a"), "截图"),
    ([Expectation(text="x")], Observation(before_image=b"", after_image=b"b"), "截图"),
])
def test_evaluate_missing_inputs_are_inconclusive(engine, fake_litellm, expectations, observation, reason):
    result = engine.evaluate(expectations, observation)
    assert result.status == "inconclusive"
    assert reason in result.error
    assert result.mismatches == []
    assert fake_litellm.calls == []


def test_evaluate_records_model_failure(engine, fake_litellm):
    fake_litellm.texts.append(RuntimeError("offline"))
    result = engine.evaluate([Expectation(text="x")], Observation(before_image=b"a", after_image=b"b"))
    assert result.status == "failed"
    assert "offline" in result.error
    assert result.mismatches == []


def test_evaluate_retries_missing_mismatches_field(engine, fake_litellm):
    fake_litellm.texts.extend(["{}", '{"mismatches": []}'])
    result = engine.evaluate([Expectation(text="x")], Observation(before_image=b"a", after_image=b"b"))
    assert result.status == "passed"
    assert len(fake_litellm.calls) == 2


def test_evaluate_records_invalid_response_as_failed(engine, fake_litellm):
    fake_litellm.texts.extend(["{}", '{"mismatches": null}'])
    result = engine.evaluate([Expectation(text="x")], Observation(before_image=b"a", after_image=b"b"))
    assert result.status == "failed"
    assert result.error


def test_evaluate_supports_explicit_inconclusive(engine, fake_litellm):
    fake_litellm.texts.append('{"status": "inconclusive", "mismatches": [], "error": "截图遮挡反馈"}')
    result = engine.evaluate([Expectation(text="x")], Observation(before_image=b"a", after_image=b"b"))
    assert result.status == "inconclusive"
    assert result.error == "截图遮挡反馈"
    assert len(fake_litellm.calls) == 1
    with pytest.raises(JudgmentError, match="截图遮挡反馈"):
        parse_mismatches('{"status": "inconclusive", "mismatches": [], "error": "截图遮挡反馈"}')


def test_evaluate_rejects_expectations_from_another_action(engine, fake_litellm):
    exps = [Expectation(text="保存提示", action_desc="click 保存")]
    result = engine.evaluate(exps, Observation(before_image=b"a", after_image=b"b", action_desc="click 删除"))
    assert result.status == "failed"
    assert "动作" in result.error
    assert fake_litellm.calls == []


def test_evaluate_rejects_invented_expectations(engine, fake_litellm):
    raw = '{"mismatches": [{"expectation": "删除确认", "observation": "y", "level": "low", "reasoning": "r"}]}'
    fake_litellm.texts.extend([raw, raw])
    result = engine.evaluate([Expectation(text="保存提示")], Observation(before_image=b"a", after_image=b"b"))
    assert result.status == "failed"
    assert "未提供" in result.error


# ---- 端到端 ----

def test_expect_then_judge_end_to_end(engine, fake_litellm):
    fake_litellm.texts.extend([
        "- 点保存应有提示",   # expect 采样第 1 次
        "- 点保存应有提示",   # expect 采样第 2 次（重复，去重后仍 1 条）
        '{"mismatches": [{"expectation": "点保存应有提示", "observation": "无反馈",'
        ' "level": "high", "reasoning": "r"}]}',  # judge
    ])
    exps = engine.expect(_ctx(), PageInfo(route="/orders"))
    assert [e.text for e in exps] == ["点保存应有提示"]
    m = engine.judge(exps, Observation(before_image=b"a", after_image=b"b", action_desc="click 保存"))
    assert len(m) == 1 and m[0].level == MismatchLevel.HIGH
