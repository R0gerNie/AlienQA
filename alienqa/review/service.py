"""HumanReview：审核服务（inbox / decide / accepted / 排序）。"""
import json
from pathlib import Path

from ..evidence.models import Severity
from .models import Decision, ReviewState

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.MAJOR: 1,
    Severity.MINOR: 2,
    Severity.TRIVIAL: 3,
}


class HumanReview:
    def __init__(self, state: ReviewState | None = None):
        self.state = state or ReviewState()

    def inbox(self, evidences) -> list:
        return list(evidences)

    def decide(self, evidence_id: str, decision, note: str = "") -> None:
        if isinstance(decision, str):
            decision = Decision(decision)
        self.state.decide(evidence_id, decision, note)

    def accepted(self, evidences) -> list:
        return [e for e in evidences if self.state.decision(e.id) == Decision.CONFIRMED]

    def sorted_evidences(self, evidences, by: str = "severity") -> list:
        if by == "alphabetical":
            return sorted(evidences, key=lambda e: e.id)
        return sorted(evidences, key=lambda e: _severity_rank(e.severity))

    def save(self, path) -> None:
        Path(path).write_text(
            json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        state = ReviewState()
        for ev_id, v in data.items():
            state.decide(ev_id, Decision(v["decision"]), v.get("note", ""))
        return cls(state)


def _severity_rank(severity) -> int:
    if isinstance(severity, Severity):
        return _SEVERITY_ORDER.get(severity, 9)
    return _SEVERITY_ORDER.get(Severity(severity), 9)
