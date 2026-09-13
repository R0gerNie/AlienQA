"""Exploration Context 数据模型与截图处理钩子。

ExplorerContext 是"陌生人（裸 LLM）"能看到的唯一上下文包；
InvestigatorContext 与它严格隔离（11 Investigation Agent 专用）。
"""
from dataclasses import dataclass, field

# 认知边界的字段词汇表：允许（白名单）与禁止（黑名单）。
ALLOWED_FIELDS = ("screenshot", "visible_text", "action_history", "navigation", "product_brief")
FORBIDDEN_FIELDS = (
    "prd",
    "dev_comments",
    "git_history",
    "known_bugs",
    "internal_rules",
    "tech_details",
)


class ScreenshotProcessor:
    """截图处理钩子：默认透传字节。

    如果后续发现性能压力，可注入子类做压缩/降采样（如 Pillow resize / JPEG），
    在 build() 里统一生效，不改动调用方。
    """

    def process(self, raw: bytes | None) -> bytes | None:
        return raw


@dataclass
class Observation:
    """当前页面的一次观察（来自 04 Browser Controller / 07 Observation Engine）。"""

    screenshot: bytes | None = None
    visible_text: str = ""


@dataclass
class ExplorerContext:
    """受限上下文包：只含白名单字段。

    forbidden 是审计块：每个黑名单字段恒为 False（表示"未进入上下文"）。
    """

    screenshot: bytes | None = None
    visible_text: str = ""
    action_history: list = field(default_factory=list)
    navigation: list = field(default_factory=list)
    product_brief: str = ""
    forbidden: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "allowed": {
                "screenshot": f"<{len(self.screenshot)} bytes>" if self.screenshot else None,
                "visible_text": self.visible_text,
                "action_history": list(self.action_history),
                "navigation": list(self.navigation),
                "product_brief": self.product_brief,
            },
            "forbidden": dict(self.forbidden),
        }


@dataclass
class InvestigatorContext:
    """11 Investigation Agent 专用上下文（与 Explorer 隔离）。"""

    source: str = ""
    dom: str = ""
    console: str = ""
    network: str = ""
    api: str = ""
    stack_trace: str = ""
    react_tree: str = ""  # 延后
    git_diff: str = ""    # 延后
    action_trace: str = ""

    def to_text(self) -> str:
        parts = []
        for label, value in (
            ("源码", self.source),
            ("DOM", self.dom),
            ("控制台", self.console),
            ("网络", self.network),
            ("API", self.api),
            ("堆栈", self.stack_trace),
            ("动作轨迹", self.action_trace),
        ):
            if value:
                parts.append(f"[{label}]\n{value}")
        return "\n\n".join(parts)
