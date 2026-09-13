"""模型路由解析与配置加载。"""
from pathlib import Path

from .models import LLMConfig

# OpenAI 裸模型名前缀：LiteLLM 直接识别，无需挂 provider。
_OPENAI_BARE_PREFIXES = ("gpt-", "o1", "o3", "o4", "text-", "dall-", "whisper-", "tts-")


def resolve_model(model: str, default_provider: str = "openai") -> str:
    """把配置里的模型名解析成 LiteLLM 可用的路由。

    - "anthropic/claude-3-5-sonnet" 这类含 "/" 的完整路由 → 原样返回。
    - "gpt-4o" 等 OpenAI 裸名 → 原样返回（LiteLLM 默认 provider 为 openai）。
    - 其它裸名（如 "claude-3-5-sonnet"）→ 挂上 default_provider。
    """
    if not model:
        return model
    if "/" in model:
        return model
    if model.lower().startswith(_OPENAI_BARE_PREFIXES):
        return model
    return f"{default_provider}/{model}"


def load_config(path: str | Path) -> LLMConfig:
    import yaml

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return LLMConfig.from_dict(data)
