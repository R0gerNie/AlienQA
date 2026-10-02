"""Exploration Context 数据模型与截图处理钩子。

ExplorerContext 是"陌生人（裸 LLM）"能看到的唯一上下文包；
InvestigatorContext 与它严格隔离（11 Investigation Agent 专用）。
"""
from dataclasses import dataclass, field
import json

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

    forbidden 仅表示未传入对应字段，不证明可见文案语义没有污染。
    """

    screenshot: bytes | None = None
    visible_text: str = ""
    action_history: list = field(default_factory=list)
    navigation: list = field(default_factory=list)
    product_brief: str = ""
    forbidden: dict = field(default_factory=dict)
    state_id: str = ""  # 浏览器状态身份，仅用于动作覆盖，不携带实现信息
    visible_history: list[dict] = field(default_factory=list)
    input_limits: dict = field(default_factory=dict)
    run_id: str = ""
    step_id: str = ""
    action_id: str = ""

    def to_dict(self) -> dict:
        return {
            "allowed": {
                "screenshot": f"<{len(self.screenshot)} bytes>" if self.screenshot else None,
                "visible_text": self.visible_text,
                "action_history": list(self.action_history),
                "navigation": list(self.navigation),
                "product_brief": self.product_brief,
                "visible_history": list(self.visible_history),
            },
            "forbidden": dict(self.forbidden),
            "input_limits": dict(self.input_limits),
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
    evidence_facts: list = field(default_factory=list)
    input_status: dict = field(default_factory=dict)

    def to_text(self) -> str:
        sections = [("保存事实", json.dumps(self.evidence_facts, ensure_ascii=False) if self.evidence_facts else "", 3000),
                    ("动作轨迹", self.action_trace, 1200), ("控制台", self.console, 500),
                    ("网络", self.network, 500), ("API", self.api, 200),
                    ("堆栈", self.stack_trace, 500), ("DOM", self.dom, 1500), ("源码", self.source, 3000)]
        truncated = [label for label, value, cap in sections if len(value) > cap]
        self.input_status.update(prompt_truncated=bool(truncated), prompt_truncated_sections=truncated,
                                 prompt_budget_chars=11500)
        status = json.dumps(self.input_status, ensure_ascii=False)
        if len(status) > 1000:
            self.input_status["prompt_truncated"] = True
        parts = ["[调查边界]\n根因和代码位置仅为假设；缺失、未执行与未知不能写成已发生。"
                 "输入总限 11500 字符，分段有界；截断部分不作为已读取内容。\n" + status[:1000]]
        for label, value, cap in sections:
            if value:
                parts.append(f"[{label}]\n{value[:cap]}" + ("\n[截断：其余内容未送入模型]" if len(value) > cap else ""))
        return "\n\n".join(parts)
