"""Expectation Engine 数据模型与最小 Observation 契约。"""
from dataclasses import dataclass, field
from enum import Enum

from ..llm.jsonutil import loads_object


class MismatchLevel(str, Enum):
    """不符严重程度。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


_LEVEL_MAP = {
    "high": MismatchLevel.HIGH, "HIGH": MismatchLevel.HIGH, "高": MismatchLevel.HIGH,
    "medium": MismatchLevel.MEDIUM, "MEDIUM": MismatchLevel.MEDIUM, "中": MismatchLevel.MEDIUM,
    "low": MismatchLevel.LOW, "LOW": MismatchLevel.LOW, "低": MismatchLevel.LOW,
}


@dataclass
class Expectation:
    """一条"陌生用户自然预期"。"""

    text: str = ""


@dataclass
class PageInfo:
    """当前页面的补充信息（ExplorerContext 里没有的元素清单）。"""

    route: str = ""
    elements: list = field(default_factory=list)  # list[str]，如 "按钮「保存」"


@dataclass
class Observation:
    """07 Observation 的最小 duck-typed 契约：07 将来产出同形状对象即可。

    判定只依赖这四个字段（action + before/after + 技术信号），不含源码/PRD。
    """

    before_image: bytes | None = None
    after_image: bytes | None = None
    action_desc: str = ""
    technical: dict = field(default_factory=dict)


@dataclass
class ExpectationMismatch:
    """一条预期不符（不是 Bug；定性/分类留给 09/11/12）。"""

    expectation: str = ""
    observation: str = ""
    level: MismatchLevel = MismatchLevel.MEDIUM
    reasoning: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "ExpectationMismatch":
        raw_level = str(d.get("level") or "").strip()
        return cls(
            expectation=str(d.get("expectation") or "").strip(),
            observation=str(d.get("observation") or "").strip(),
            level=_LEVEL_MAP.get(raw_level, MismatchLevel.MEDIUM),
            reasoning=str(d.get("reasoning") or "").strip(),
        )


def parse_mismatch(text: str) -> ExpectationMismatch | None:
    """解析 judge 的 JSON 输出；matched=true 时返回 None。失败抛 ValueError。"""
    data = loads_object(text)
    if data.get("matched") in (True, "true", "True"):
        return None
    return ExpectationMismatch.from_dict(data)
