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
    visible: dict | None = None  # bounded pre-action identity; never locator/value internals

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
            visible=d.get("visible"),
        )


@dataclass
class Action:
    """结构化动作：LLM 只产出 Action，不直接操作浏览器。"""

    type: str  # click | hover | type | press | select | blur
    target: Target = field(default_factory=Target)
    text: str = ""  # type/press 的输入；select 的 option value
    input_branch: str = ""  # deterministic semantic input recipe, not the private value

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        if not isinstance(d, dict):
            raise ValueError(f"action 需要 dict，收到 {type(d)!r}")
        return cls(
            type=d.get("type", ""),
            target=Target.from_dict(d.get("target") or {}),
            text=d.get("text", ""),
            input_branch=d.get("input_branch", ""),
        )


def describe_visible_action(action) -> str:
    """A visible label only: locator internals and typed values stay outside LLM text."""
    if action is None:
        return ""
    if isinstance(action, dict):
        kind, target = action.get("type", ""), action.get("target", {})
    else:
        kind, target = getattr(action, "type", ""), getattr(action, "target", None)
    get = target.get if isinstance(target, dict) else lambda key, default=None: getattr(target, key, default)
    label = get("text") or get("name") or get("label")
    if not label:
        identity = visible_target(action)
        label = f"无文案 {identity.get('role') or '控件'}"
        position = identity.get("position")
        if position:
            label += f"（页面位置 x={position['x']}, y={position['y']}）"
        if identity.get("popup"):
            label += f"，可展开 {identity['popup']}"
    from .runtime import clean_message
    return clean_message(f"{kind} {label or '当前控件'}").strip()[:200]


def visible_target(action) -> dict:
    """Whitelisted observable target identity; tolerate old Actions and untrusted dictionaries."""
    import math
    from .runtime import clean_message
    target = action.get("target", {}) if isinstance(action, dict) else getattr(action, "target", None)
    get = target.get if isinstance(target, dict) else lambda key, default=None: getattr(target, key, default)
    source = get("visible") or {}
    if not isinstance(source, dict):
        source = {}
    out = {}
    for key in ("role", "label"):
        value = get("role") if key == "role" else get("text") or get("name") or get("label")
        value = value or source.get(key)
        if isinstance(value, str):
            out[key] = clean_message(value)[:200]
    if source.get("popup") in {"menu", "listbox", "dialog", "true", "tree", "grid"}:
        out["popup"] = source["popup"]
    for key in ("focused", "expanded"):
        if type(source.get(key)) is bool:
            out[key] = source[key]
    if source.get("value_state") in {"empty", "nonempty"}:
        out["value_state"] = source["value_state"]
    position = source.get("position")
    if isinstance(position, dict) and all(type(position.get(k)) in {int, float} and math.isfinite(position[k])
                                         for k in ("x", "y", "width", "height")):
        out["position"] = {k: round(position[k], 1) for k in ("x", "y", "width", "height")}
    return out
