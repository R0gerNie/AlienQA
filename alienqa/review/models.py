"""Human Review + Report 数据模型。"""
from dataclasses import dataclass, field
from enum import Enum


class Decision(str, Enum):
    """四种开发者决定，pending 表示尚未处理。"""

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

    @classmethod
    def from_dict(cls, data) -> "ReviewState":
        if not isinstance(data, dict):
            raise ValueError("审核状态需要 JSON 对象")
        state = cls()
        for key, value in data.items():
            if not isinstance(key, str) or not key or not isinstance(value, dict):
                raise ValueError("无效审核记录")
            note = value.get("note", "")
            if not isinstance(note, str):
                raise ValueError("备注必须是字符串")
            try:
                decision = Decision(value.get("decision"))
            except (ValueError, TypeError) as exc:
                raise ValueError("无效审核决定") from exc
            state.decide(key, decision, note)
        return state


@dataclass
class Report:
    html: str = ""
    accepted_count: int = 0
    total_count: int = 0
    mode: str = "confirmed"
    displayed_count: int = 0

    def to_dict(self) -> dict:
        return {"html": self.html, "accepted_count": self.accepted_count, "total_count": self.total_count,
                "mode": self.mode, "displayed_count": self.displayed_count}
