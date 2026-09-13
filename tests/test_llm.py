"""LLM 层测试：模型解析、角色温度、故障回退、视觉消息格式、三角色 prompt（mock LiteLLM）。"""
import base64

import pytest

from alienqa.llm import (
    LLMClient,
    LLMConfig,
    LlmRoles,
    Role,
    RoleConfig,
    encode_image,
    load_config,
    resolve_model,
)


class _FakeChoice:
    def __init__(self, text):
        self.message = type("M", (), {"content": text})()


class _FakeResp:
    def __init__(self, text, model):
        self.choices = [_FakeChoice(text)]
        self.model = model
        self.usage = None


class _FakeLiteLLM:
    """按 behavior 列表依次返回文本或抛异常，并记录每次调用的 kwargs。"""

    def __init__(self, behavior):
        self.behavior = list(behavior)
        self.calls = []

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        item = self.behavior.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeResp(text=item, model=kwargs["model"])


@pytest.fixture
def config():
    return LLMConfig(roles={
        "gist": RoleConfig(model="gpt-4o-mini", temperature=0.1),
        "expectation": RoleConfig(model="gpt-4o-mini", temperature=0.8),
        "judge": RoleConfig(model="gpt-4o", temperature=0.2, fallbacks=["anthropic/claude-3-5-sonnet"]),
    })


@pytest.fixture
def client(config, monkeypatch):
    fake = _FakeLiteLLM(["ok"])
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: fake)
    c = LLMClient(config)
    c._fake = fake
    return c


# ---- 模型解析 ----

def test_resolve_model_bare_openai():
    assert resolve_model("gpt-4o") == "gpt-4o"


def test_resolve_model_bare_with_provider():
    assert resolve_model("claude-3-5-sonnet-20241022", "anthropic") == "anthropic/claude-3-5-sonnet-20241022"


def test_resolve_model_full_route_passthrough():
    assert resolve_model("dashscope/qwen-vl-max") == "dashscope/qwen-vl-max"


# ---- 角色温度与模型 ----

def test_gist_uses_low_temperature(client):
    client.complete(Role.GIST, [{"role": "user", "content": "hi"}])
    assert client._fake.calls[0]["temperature"] == 0.1
    assert client._fake.calls[0]["model"] == "gpt-4o-mini"


def test_expectation_uses_high_temperature(client):
    client.complete(Role.EXPECTATION, [{"role": "user", "content": "hi"}])
    assert client._fake.calls[0]["temperature"] == 0.8


# ---- 故障回退（模型轮换）----

def test_fallback_on_primary_failure(client, monkeypatch):
    fake = _FakeLiteLLM([RuntimeError("boom"), "fallback-ok"])
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: fake)
    resp = client.complete(Role.JUDGE, [{"role": "user", "content": "hi"}])
    assert resp.text == "fallback-ok"
    assert resp.model == "anthropic/claude-3-5-sonnet"
    assert [c["model"] for c in fake.calls] == ["gpt-4o", "anthropic/claude-3-5-sonnet"]


def test_all_models_fail_raises(client, monkeypatch):
    fake = _FakeLiteLLM([RuntimeError("a"), RuntimeError("b")])
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: fake)
    with pytest.raises(RuntimeError, match="全部失败"):
        client.complete(Role.JUDGE, [{"role": "user", "content": "hi"}])


def test_unconfigured_role_raises(config):
    c = LLMClient(LLMConfig(roles={}))
    with pytest.raises(ValueError, match="未配置"):
        c.complete("judge", [{"role": "user", "content": "hi"}])


# ---- 视觉消息格式 ----

def test_vision_message_contains_image_url(client):
    client.complete_vision(Role.JUDGE, "compare", [b"\x89PNG-fake"])
    call = client._fake.calls[0]
    content = call["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "compare"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_encode_image_bytes():
    data_url = encode_image(b"hello")
    assert data_url.startswith("data:image/png;base64,")
    assert base64.b64decode(data_url.split(",", 1)[1]) == b"hello"


# ---- 三角色 prompt ----

def test_summarize_gist_calls_gist_role(client):
    roles = LlmRoles(client)
    roles.summarize_gist("MY README", "pages: /login")
    call = client._fake.calls[0]
    assert call["model"] == "gpt-4o-mini"
    assert "MY README" in call["messages"][0]["content"]


def test_generate_expectations_samples_and_dedups(client):
    fake = _FakeLiteLLM(["- 点保存应有提示\n- 页面状态应变化", "- 点保存应有提示\n- 缺少加载反馈"])
    from alienqa.llm.client import _litellm as _orig  # noqa: F401

    import alienqa.llm.client as client_mod

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(client_mod, "_litellm", lambda: fake)
    try:
        roles = LlmRoles(client)
        out = roles.generate_expectations("电商后台", "有个保存按钮", samples=2)
        assert "点保存应有提示" in out
        assert "页面状态应变化" in out
        assert "缺少加载反馈" in out
        assert len(out) == 3  # 去重后
    finally:
        monkeypatch.undo()


def test_judge_uses_vision(client):
    roles = LlmRoles(client)
    roles.judge("点击保存", "应有成功提示", b"before", b"after")
    call = client._fake.calls[0]
    content = call["messages"][0]["content"]
    assert len(content) == 3  # text + 2 images
    assert "点击保存" in content[0]["text"]


# ---- 配置加载（pyyaml）----

def test_load_config_from_yaml(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "llm:\n"
        "  default_provider: openai\n"
        "  roles:\n"
        "    gist:\n"
        "      model: gpt-4o-mini\n"
        "      temperature: 0.1\n"
        "    judge:\n"
        "      model: gpt-4o\n"
        "      fallbacks: [anthropic/claude-3-5-sonnet]\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.default_provider == "openai"
    assert cfg.role(Role.GIST).model == "gpt-4o-mini"
    assert cfg.role(Role.GIST).temperature == 0.1
    assert cfg.role(Role.JUDGE).fallbacks == ["anthropic/claude-3-5-sonnet"]


def test_load_config_project_yaml():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    cfg = load_config(root / "config" / "config.yaml")
    assert set(cfg.roles) == {"gist", "expectation", "judge", "visual", "investigator", "reporter"}
    assert cfg.role(Role.JUDGE).model == "dashscope/qwen-vl-plus"
    assert cfg.role(Role.VISUAL).model == "dashscope/qwen-vl-plus"
    assert cfg.role(Role.GIST).model == "deepseek/deepseek-chat"
    assert cfg.role(Role.INVESTIGATOR).model == "deepseek/deepseek-chat"
    assert cfg.role(Role.REPORTER).model == "deepseek/deepseek-chat"
    assert cfg.role(Role.EXPECTATION).temperature == 0.8
    assert cfg.role(Role.VISUAL).temperature == 0.1
