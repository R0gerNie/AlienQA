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

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "reproduced": self.reproduced,
            "match_score": self.match_score,
            "replay": self.replay,
            "note": self.note,
        }
