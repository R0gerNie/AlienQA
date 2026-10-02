"""Replay Engine 数据模型。"""
from dataclasses import dataclass, field


@dataclass
class ReplayResult:
    """一次回放的结果。"""

    evidence_id: str = ""
    reproduced: bool = False
    match_score: float = 0.0
    replay: dict = field(default_factory=dict)
    note: str = ""  # reproduced=false 时的降权提示
    status: str = "inconclusive"
    matched_signals: dict = field(default_factory=dict)
    interrupted_step_id: str | None = None
    executed_steps: list = field(default_factory=list)
    phase: str = "package"
    preconditions: dict = field(default_factory=dict)
    target_window: dict = field(default_factory=dict)
    matched_basis: list = field(default_factory=list)
    limits: list = field(default_factory=list)

    def to_dict(self, include_replay: bool = False) -> dict:
        """Public result omits session secrets; internal callers can request the package."""
        result = {
            "evidence_id": self.evidence_id,
            "reproduced": self.reproduced,
            "match_score": self.match_score,
            "note": self.note,
            "status": self.status,
            "matched_signals": self.matched_signals,
            "interrupted_step_id": self.interrupted_step_id,
            "executed_steps": self.executed_steps,
            "phase": self.phase,
            "preconditions": self.preconditions,
            "target_window": self.target_window,
            "matched_basis": self.matched_basis,
            "limits": self.limits,
        }
        if include_replay:
            result["replay"] = self.replay
        return result
