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


@dataclass
class Action:
    """结构化动作：LLM 只产出 Action，不直接操作浏览器。"""

    type: str  # click | hover | type | press
    target: Target = field(default_factory=Target)
    text: str = ""  # type/press 的输入
