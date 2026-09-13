"""Settings 存储与 provider 抽取的单元测试。"""
import os

from alienqa.llm import LLMConfig, RoleConfig
from alienqa.ui import Settings, SettingsStore, providers_from_config


def _cfg() -> LLMConfig:
    return LLMConfig(roles={
        "gist": RoleConfig(model="deepseek/deepseek-chat"),
        "judge": RoleConfig(model="dashscope/qwen-vl-plus"),
        "visual": RoleConfig(model="dashscope/qwen-vl-max"),
        "reporter": RoleConfig(model="deepseek/deepseek-chat"),
    })


def test_providers_from_config():
    assert providers_from_config(_cfg()) == ["dashscope", "deepseek"]


def test_providers_includes_default_provider_for_bare_models():
    cfg = LLMConfig(default_provider="openai", roles={"gist": RoleConfig(model="gpt-4o-mini")})
    assert providers_from_config(cfg) == ["openai"]


def test_settings_roundtrip(tmp_path):
    store = SettingsStore(tmp_path / "config.local.yaml")
    s = Settings(llm_keys={"deepseek": "sk-a", "dashscope": "sk-b"}, project_path="d:/p", unit="登录页")
    store.save(s)
    loaded = store.load()
    assert loaded.llm_keys == {"deepseek": "sk-a", "dashscope": "sk-b"}
    assert loaded.project_path == "d:/p"
    assert loaded.unit == "登录页"


def test_settings_apply_to_env():
    Settings(llm_keys={"deepseek": "sk-a", "dashscope": "sk-b"}).apply_to_env()
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-a"
    assert os.environ["DASHSCOPE_API_KEY"] == "sk-b"


def test_settings_skip_empty_keys(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    Settings(llm_keys={"deepseek": ""}).apply_to_env()
    assert "DEEPSEEK_API_KEY" not in os.environ


def test_settings_instructions_roundtrip(tmp_path):
    store = SettingsStore(tmp_path / "config.local.yaml")
    store.save(Settings(unit="登录表单", instructions="错误密码应有提示"))
    loaded = store.load()
    assert loaded.unit == "登录表单"
    assert loaded.instructions == "错误密码应有提示"
