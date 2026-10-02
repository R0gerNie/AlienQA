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
    issue_id: str = ""                                 # 10 去重回写关联
    action: dict = field(default_factory=dict)        # 触发动作（type + target）
    expectation: str = ""                              # 预期（what was expected）
    observation_summary: str = ""                      # 实际（what happened）
    reasoning: str = ""                                # 为什么预期合理（why reasonable）
    severity: Severity = Severity.MINOR
    classification: str = "other"
    confidence: float | None = 0.5
    timestamp: str = ""
    artifacts: dict = field(default_factory=dict)      # screenshots/dom/console/network 路径
    replay: dict = field(default_factory=dict)         # 13 用，非空才完整
    before_state_id: str = ""
    after_state_id: str = ""
    schema_version: int | None = None
    finding_kind: str | None = None
    expectation_basis: dict | None = None
    run_id: str = ""
    step_id: str | None = None
    action_id: str | None = None
    source_record_ids: list[str] = field(default_factory=list)
    expectation_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "issue_id": self.issue_id,
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
            "before_state_id": self.before_state_id,
            "after_state_id": self.after_state_id,
            "schema_version": self.schema_version,
            "finding_kind": self.finding_kind,
            "expectation_basis": self.expectation_basis,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "action_id": self.action_id,
            "source_record_ids": list(self.source_record_ids),
            "expectation_id": self.expectation_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Evidence":
        """Load current and older evidence documents without requiring new fields."""
        if data.get("schema_version") not in (None, 1, 2):
            raise ValueError("不支持的 Evidence schema_version")
        if data.get("finding_kind") not in (None, "technical_anomaly", "cognitive_mismatch"):
            raise ValueError("无效 finding_kind")
        if data.get("finding_kind") == "cognitive_mismatch" and not valid_basis(data.get("expectation_basis")):
            raise ValueError("认知证据缺少有效的事前依据")
        if data.get("finding_kind") == "technical_anomaly" and data.get("expectation_basis") is not None:
            raise ValueError("技术证据不能虚构认知依据")
        values = {name: data[name] for name in cls.__dataclass_fields__ if name in data}
        values["severity"] = Severity(data.get("severity") or Severity.MINOR.value)
        return cls(**values)

    def is_complete(self) -> bool:
        """证据完整 = 含 replay 且非空（planbook：否则视为不完整证据）。"""
        return bool(self.replay.get("url") and self.artifacts.get("before") and self.artifacts.get("after")
                    and self.artifacts.get("technical") and not self.artifacts.get("missing"))


def valid_basis(basis) -> bool:
    return (isinstance(basis, dict) and basis.get("type") in
            {"visible_copy", "interaction_convention", "observed_behavior"}
            and isinstance(basis.get("reference"), str) and bool(basis["reference"].strip()))
