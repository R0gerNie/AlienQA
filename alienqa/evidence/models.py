"""Evidence Engine 数据模型：4 级严重度 + 分类 + 八要素。"""
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """证据严重度（≥4 级，表示不同程度的问题）。"""

    CRITICAL = "critical"   # 白屏/崩溃/500：功能不可用
    MAJOR = "major"         # 明显不符预期 + 技术信号
    MINOR = "minor"         # 体验问题（缺反馈/语义不一致）
    TRIVIAL = "trivial"     # 观感/文案瑕疵


# 分类词表（与 planbook 09 对齐）
CLASSIFICATIONS = ("technical_bug", "ux_ambiguity", "missing_feedback", "misleading_copy", "other")


@dataclass
class Evidence:
    """一条疑似问题证据：八要素 + 严重度 + 置信度 + replay。"""

    id: str = ""
    action: dict = field(default_factory=dict)        # 触发动作（type + target）
    expectation: str = ""                              # 预期（what was expected）
    observation_summary: str = ""                      # 实际（what happened）
    reasoning: str = ""                                # 为什么预期合理（why reasonable）
    severity: Severity = Severity.MINOR
    classification: str = "other"
    confidence: float = 0.5
    timestamp: str = ""
    artifacts: dict = field(default_factory=dict)      # screenshots/dom/console/network 路径
    replay: dict = field(default_factory=dict)         # 13 用，非空才完整

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "action": self.action,
            "expectation": self.expectation,
            "observation_summary": self.observation_summary,
            "reasoning": self.reasoning,
            "severity": self.severity.value,
            "classification": self.classification,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "artifacts": self.artifacts,
            "replay": self.replay,
        }

    def is_complete(self) -> bool:
        """证据完整 = 含 replay 且非空（planbook：否则视为不完整证据）。"""
        return bool(self.replay)
