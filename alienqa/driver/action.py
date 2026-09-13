"""结构化 Action 与 Target 模型。"""
from dataclasses import dataclass, field


@dataclass
class Target:
    """定位目标：text / role / selector / (x, y) 至少其一。"""

    text: str | None = None
    role: str | None = None
    selector: str | None = None
    x: int | None = None
    y: int | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Target":
        if not isinstance(d, dict):
            return cls()
        return cls(
            text=d.get("text"),
            role=d.get("role"),
            selector=d.get("selector"),
            x=d.get("x"),
            y=d.get("y"),
        )


@dataclass
class Action:
    """结构化动作：LLM 只产出 Action，不直接操作浏览器。"""

    type: str  # click | hover | type | press
    target: Target = field(default_factory=Target)
    text: str = ""  # type/press 的输入

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        if not isinstance(d, dict):
            raise ValueError(f"action 需要 dict，收到 {type(d)!r}")
        return cls(
            type=d.get("type", ""),
            target=Target.from_dict(d.get("target") or {}),
            text=d.get("text", ""),
        )
