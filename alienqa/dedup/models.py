"""Evidence Deduplicator 数据模型：Issue / Vector。"""
from dataclasses import dataclass, field

from ..evidence.models import Severity


@dataclass
class Vector:
    """一条 Evidence 的嵌入（deterministic 用 text_grams，llm 用 text_vec）。"""

    text_grams: frozenset | None = None
    text_vec: tuple | None = None
    screenshot_hash: int | None = None


@dataclass
class Issue:
    """多条同根因证据归并而成。"""

    id: str = ""
    title: str = ""
    evidence_ids: list = field(default_factory=list)
    root_cause_candidate: str = ""  # 占位，11 再填
    severity: Severity = Severity.MINOR

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "evidence_ids": list(self.evidence_ids),
            "root_cause_candidate": self.root_cause_candidate,
            "severity": self.severity.value,
        }
