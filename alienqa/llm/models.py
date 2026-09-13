"""LLM 层数据模型与配置。"""
from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    """五种 LLM 角色（对应 planbook 02/07/08/11）。"""

    GIST = "gist"                # A 主旨加载：便宜快速、低温度
    EXPECTATION = "expectation"  # B 预期生成：高温度、采样取并集
    JUDGE = "judge"              # C 盲判：强视觉模型、低温度
    VISUAL = "visual"            # D 视觉观察：描述视觉变化、低温度
    INVESTIGATOR = "investigator"  # E 专家调查：可看源码、低温度


@dataclass
class RoleConfig:
    """单个角色的模型与采样配置。"""

    model: str = ""                # LiteLLM 路由名（provider/model）或裸名
    temperature: float = 0.2
    fallbacks: list = field(default_factory=list)  # 失败自动回退的模型列表
    max_tokens: int | None = None


@dataclass
class LLMConfig:
    """全局 LLM 配置：三角色各自独立，可任意轮换模型。"""

    default_provider: str = "openai"
    request_timeout: float = 120.0
    roles: dict = field(default_factory=dict)  # Role.value -> RoleConfig

    @classmethod
    def from_dict(cls, data: dict) -> "LLMConfig":
        llm = data.get("llm", data) if isinstance(data, dict) else {}
        cfg = cls(
            default_provider=llm.get("default_provider", "openai"),
            request_timeout=float(llm.get("request_timeout", 120.0)),
        )
        for key, val in (llm.get("roles") or {}).items():
            cfg.roles[key] = RoleConfig(
                model=val.get("model", ""),
                temperature=float(val.get("temperature", 0.2)),
                fallbacks=list(val.get("fallbacks") or []),
                max_tokens=val.get("max_tokens"),
            )
        return cfg

    def role(self, role) -> RoleConfig | None:
        if isinstance(role, Role):
            role = role.value
        return self.roles.get(role)


@dataclass
class LLMResponse:
    text: str
    model: str = ""
    role: str = ""
    usage: dict = field(default_factory=dict)
