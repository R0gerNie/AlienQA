"""用户设置：LLM 密钥 + 项目路径 + 测试单元，持久化到 config.local.yaml（gitignored）。

设计约定：
- 密钥按 provider 存储（deepseek / dashscope / openai / ...），同 provider 的模型共用一把 key，
  不同 provider 允许填相同值（"允许相同"）。
- 运行时 apply_to_env() 把密钥写入环境变量，供 litellm 读取。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# provider → 环境变量名（litellm 按这些变量读密钥）
PROVIDER_ENV = {
    "deepseek": "DEEPSEEK_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama": "",  # 本地部署，无需密钥
}


def providers_from_config(config) -> list:
    """从 LLMConfig 的角色模型里抽取去重的 provider 列表。"""
    providers = set()
    for rc in config.roles.values():
        model = (rc.model or "").strip()
        if not model:
            continue
        if "/" in model:
            providers.add(model.split("/", 1)[0])
        else:
            providers.add(config.default_provider or "openai")
    return sorted(providers)


@dataclass
class Settings:
    llm_keys: dict = field(default_factory=dict)  # provider -> key
    project_path: str = ""
    unit: str = ""
    instructions: str = ""

    def apply_to_env(self) -> None:
        for provider, key in self.llm_keys.items():
            if not key:
                continue
            env_name = PROVIDER_ENV.get(provider) or f"{provider.upper()}_API_KEY"
            if env_name:
                os.environ[env_name] = key

    def to_dict(self) -> dict:
        return {
            "llm_keys": dict(self.llm_keys),
            "project_path": self.project_path,
            "unit": self.unit,
            "instructions": self.instructions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        data = data or {}
        return cls(
            llm_keys={str(k): str(v) for k, v in (data.get("llm_keys") or {}).items()},
            project_path=str(data.get("project_path") or ""),
            unit=str(data.get("unit") or ""),
            instructions=str(data.get("instructions") or ""),
        )


class SettingsStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return Settings.from_dict(data)

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.safe_dump(settings.to_dict(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
