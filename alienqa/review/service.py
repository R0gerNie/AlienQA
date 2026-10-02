"""HumanReview：审核服务（inbox / decide / accepted / 排序）。"""
from pathlib import Path

from ..evidence.models import Severity
from .models import Decision, ReviewState
from ..persistence import atomic_write_json
from ..run_writer import read_json, StorageError

REPORT_FILES = {"analysis": "analysis.html", "confirmed": "report.html"}
TERMINAL_STATUSES = {"done", "partial", "error", "timeout", "cancelled"}
DECISION_LABELS = {"pending": "待审", "confirmed": "确认问题", "rejected": "不采信",
                   "by-design": "按设计", "skipped": "暂跳过"}


def parse_decision(payload):
    if not isinstance(payload, dict):
        raise ValueError("需要 JSON 对象")
    evidence_id, value, note = payload.get("evidence_id"), payload.get("decision"), payload.get("note", "")
    if not isinstance(evidence_id, str) or not evidence_id.strip():
        raise ValueError("evidence_id 必须是非空字符串")
    if not isinstance(value, str) or value not in {"confirmed", "rejected", "by-design", "skipped"}:
        raise ValueError("decision 只允许 confirmed/rejected/by-design/skipped")
    if not isinstance(note, str):
        raise ValueError("note 必须是字符串")
    return evidence_id, Decision(value), note


def report_mode(value):
    if value not in REPORT_FILES:
        raise ValueError("mode 只允许 analysis/confirmed")
    return value


def invalidate_report_paths(paths):
    for path in paths:
        Path(path).unlink(missing_ok=True)


def evidence_row(e, state, run_dir=None):
    from .report import _image, _technical
    return {"id": e.id, "severity": e.severity.value, "expectation": e.expectation,
            "decision": state.decision(e.id).value, "note": state.note(e.id),
            "finding_kind": e.finding_kind, "basis": e.expectation_basis,
            "observation": e.observation_summary, "reasoning": e.reasoning,
            "action": e.action, "artifacts": e.artifacts, "source_record_ids": e.source_record_ids,
            "technical": _technical(e, run_dir),
            "images": "".join(_image(e.artifacts.get(key), label, run_dir) for key, label in
                              (("before", "动作前"), ("after", "动作后")))}

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
        atomic_write_json(Path(path), self.state.to_dict())

    @classmethod
    def load(cls, path):
        try:
            return cls(ReviewState.from_dict(read_json(Path(path))))
        except ValueError as exc:
            raise StorageError(f"{path}: {exc}") from exc


def _severity_rank(severity) -> int:
    if isinstance(severity, Severity):
        return _SEVERITY_ORDER.get(severity, 9)
    return _SEVERITY_ORDER.get(Severity(severity), 9)
