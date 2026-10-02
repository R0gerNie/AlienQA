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
    name: str | None = None
    label: str | None = None
    scope: str | None = None  # visible form/dialog CSS scope, main page only
    viewport: dict | None = None  # coordinate replay precondition

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
            name=d.get("name"), label=d.get("label"), scope=d.get("scope"),
            viewport=d.get("viewport"),
        )


@dataclass
class Action:
    """结构化动作：LLM 只产出 Action，不直接操作浏览器。"""

    type: str  # click | hover | type | press | select | blur
    target: Target = field(default_factory=Target)
    text: str = ""  # type/press 的输入；select 的 option value

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        if not isinstance(d, dict):
            raise ValueError(f"action 需要 dict，收到 {type(d)!r}")
        return cls(
            type=d.get("type", ""),
            target=Target.from_dict(d.get("target") or {}),
            text=d.get("text", ""),
        )


def describe_visible_action(action) -> str:
    """A visible label only: locator internals and typed values stay outside LLM text."""
    if action is None:
        return ""
    if isinstance(action, dict):
        kind, target = action.get("type", ""), action.get("target", {})
    else:
        kind, target = getattr(action, "type", ""), getattr(action, "target", None)
    label = target.get("text", "") if isinstance(target, dict) else getattr(target, "text", "")
    from .runtime import clean_message
    return clean_message(f"{kind} {label or '当前控件'}").strip()[:200]
