"""Expectation Engine 数据模型与最小 Observation 契约。"""
from alienqa.i18n import t as tr

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from ..llm.jsonutil import loads_object
from ..observation.models import Observation  # 07 的 canonical Observation，08 duck-typing 消费


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
    action_desc: str = ""  # 空值仅用于兼容未绑定动作的旧调用。
    expectation_basis: dict | None = None
    id: str = ""
    run_id: str = ""
    step_id: str = ""
    action_id: str = ""
    prompt_version: str = ""


@dataclass
class PageInfo:
    """当前页面的补充信息（ExplorerContext 里没有的元素清单）。"""

    route: str = ""
    elements: list = field(default_factory=list)  # list[str]，如 "按钮「保存」"


@dataclass
class ExpectationMismatch:
    """一条预期不符（不是 Bug；定性/分类留给 09/11/12）。"""

    expectation: str = ""
    observation: str = ""
    level: MismatchLevel = MismatchLevel.MEDIUM
    reasoning: str = ""
    expectation_id: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "ExpectationMismatch":
        raw_level = str(d.get("level") or "").strip()
        return cls(
            expectation=str(d.get("expectation") or "").strip(),
            observation=str(d.get("observation") or "").strip(),
            level=_LEVEL_MAP.get(raw_level, MismatchLevel.MEDIUM),
            reasoning=str(d.get("reasoning") or "").strip(),
            expectation_id=str(d.get("expectation_id") or "").strip(),
        )


@dataclass
class JudgmentResult:
    """判定结果；只有 passed 表示所有本次动作预期都得到验证。"""

    status: Literal["passed", "mismatch", "failed", "inconclusive"]
    mismatches: list[ExpectationMismatch] = field(default_factory=list)
    error: str = ""
    unverifiable_expectation_ids: list[str] = field(default_factory=list)


class JudgmentError(ValueError):
    """兼容 judge() 的列表接口无法表达失败或无法判断时抛出的错误。"""

    def __init__(self, message: str, status: str = "failed"):
        super().__init__(message)
        self.status = status
        self.error = message


def parse_judgment(text: str) -> JudgmentResult:
    """严格验证盲判 JSON；省略 status 的旧响应仍须显式提供 mismatches。"""
    data = loads_object(text)
    if "mismatches" not in data or not isinstance(data["mismatches"], list):
        raise ValueError(tr("判定输出必须包含 mismatches 列表"))
    mismatches = []
    for item in data["mismatches"]:
        if not isinstance(item, dict):
            raise ValueError(tr("mismatches 的每项必须为对象"))
        for key in ("expectation", "observation", "level", "reasoning"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(tr("mismatch.{key} 必须为非空字符串", key=key))
        if item["level"].strip() not in _LEVEL_MAP:
            raise ValueError(tr("mismatch.level 必须为 high、medium 或 low"))
        mismatches.append(ExpectationMismatch.from_dict(item))

    inferred_status = "mismatch" if mismatches else "passed"
    status = data.get("status", inferred_status)
    unverifiable = data.get("unverifiable_expectation_ids", [])
    if (not isinstance(unverifiable, list) or any(not isinstance(i, str) or not i.strip() for i in unverifiable)
            or len(set(unverifiable)) != len(unverifiable)):
        raise ValueError(tr("unverifiable_expectation_ids 必须是无重复的预期 ID 数组"))
    if status not in ("passed", "mismatch", "failed", "inconclusive"):
        raise ValueError(tr("判定 status 无效"))
    if status in ("passed", "mismatch"):
        if status != inferred_status:
            raise ValueError(tr("判定 status 与 mismatches 不一致"))
        if status == "passed" and unverifiable:
            raise ValueError(tr("存在无法判断的预期不能 passed"))
        error = data.get("error", "")
        if unverifiable and (not isinstance(error, str) or not error.strip()):
            raise ValueError(tr("无法判断的预期必须提供 error 原因"))
        return JudgmentResult(status=status, mismatches=mismatches,
                              error=error if unverifiable else "", unverifiable_expectation_ids=unverifiable)
    if mismatches:
        raise ValueError(tr("failed/inconclusive 不能同时包含 mismatch"))
    error = data.get("error")
    if not isinstance(error, str) or not error.strip():
        raise ValueError(tr("failed/inconclusive 必须提供非空 error 原因"))
    return JudgmentResult(status=status, error=error.strip(), unverifiable_expectation_ids=unverifiable)


def parse_mismatches(text: str) -> list[ExpectationMismatch]:
    """兼容列表解析入口；无法判断或失败绝不伪装成空的通过结果。"""
    result = parse_judgment(text)
    if result.status in ("failed", "inconclusive"):
        raise JudgmentError(result.error, status=result.status)
    return result.mismatches
