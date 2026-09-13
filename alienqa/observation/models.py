"""Observation Engine 数据模型：视觉观察 + 运行时观察 + 合并 Observation。

Observation 是 07 的 canonical 输出；08 Expectation Engine 直接 duck-typing 消费
（before_image / after_image / action_desc / technical）。
"""
from dataclasses import dataclass, field


@dataclass
class VisualObservation:
    """视觉观察：人眼看到的变化 + 白屏分。"""

    changes: list = field(default_factory=list)   # 视觉变化标签
    blank_screen_score: float = 0.0                # 0=正常 1=白屏
    summary: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "VisualObservation":
        return cls(
            changes=_as_str_list(d.get("changes")),
            blank_screen_score=float(d.get("blank_screen_score") or 0.0),
            summary=str(d.get("summary") or "").strip(),
        )


@dataclass
class RuntimeObservation:
    """运行时观察：确定性 hook 采集，无 LLM。"""

    console_errors: list = field(default_factory=list)
    network_failures: list = field(default_factory=list)
    http_status: dict = field(default_factory=dict)   # {path: status}
    js_exceptions: list = field(default_factory=list)
    resource_failures: list = field(default_factory=list)  # 细分延后（planbook 开放问题）
    url: str = ""
    storage: dict = field(default_factory=dict)       # 延后（planbook 开放问题）


@dataclass
class Observation:
    """07 的 canonical 观察包。"""

    before_image: bytes | None = None
    after_image: bytes | None = None
    action_desc: str = ""
    visual: VisualObservation = field(default_factory=VisualObservation)
    runtime: RuntimeObservation = field(default_factory=RuntimeObservation)

    @property
    def technical(self) -> dict:
        """拍平成 08 judge 需要的技术信号。"""
        return {
            "console_errors": list(self.runtime.console_errors),
            "network_failures": list(self.runtime.network_failures),
            "http_status": dict(self.runtime.http_status),
            "js_exceptions": list(self.runtime.js_exceptions),
            "resource_failures": list(self.runtime.resource_failures),
            "url": self.runtime.url,
        }


def _as_str_list(value) -> list:
    """把 LLM 可能给出的 str/list 统一成 list[str]，过滤空值。"""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        items = []
    out = []
    for it in items:
        if isinstance(it, (str, int, float)) and str(it).strip():
            out.append(str(it).strip())
    return out
