"""Human Review + Report 数据模型。"""
from dataclasses import dataclass, field
from enum import Enum


class Decision(str, Enum):
    """审核决策（四态 + pending，UI 只暴露 confirmed/rejected）。"""

    PENDING = "pending"        # 初始
    CONFIRMED = "confirmed"    # 采信
    REJECTED = "rejected"      # 不采信
    BY_DESIGN = "by-design"
    SKIPPED = "skipped"


@dataclass
class ReviewState:
    """evidence_id -> (decision, note)。"""

    _decisions: dict = field(default_factory=dict)

    def decide(self, evidence_id: str, decision: Decision, note: str = "") -> None:
        self._decisions[evidence_id] = (decision, note)

    def decision(self, evidence_id: str) -> Decision:
        return self._decisions.get(evidence_id, (Decision.PENDING, ""))[0]

    def note(self, evidence_id: str) -> str:
        return self._decisions.get(evidence_id, (Decision.PENDING, ""))[1]

    def to_dict(self) -> dict:
        return {k: {"decision": d.value, "note": n} for k, (d, n) in self._decisions.items()}


@dataclass
class Report:
    html: str = ""
    accepted_count: int = 0
    total_count: int = 0

    def to_dict(self) -> dict:
        return {"html": self.html, "accepted_count": self.accepted_count, "total_count": self.total_count}
