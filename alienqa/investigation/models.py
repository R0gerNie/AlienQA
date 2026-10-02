"""Investigation 数据模型。"""
from dataclasses import dataclass, field

from ..llm.jsonutil import loads_object


@dataclass
class Investigation:
    """一次专家调查的产出。"""

    issue_id: str = ""
    root_cause_hypothesis: str = ""
    reproduction_steps: list = field(default_factory=list)
    technical_evidence: dict = field(default_factory=dict)
    affected_components: list = field(default_factory=list)
    status: str = "completed"
    error: str = ""
    evidence_ids: list = field(default_factory=list)
    input_status: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict, issue_id: str = "") -> "Investigation":
        return cls(
            issue_id=issue_id,
            root_cause_hypothesis=str(d.get("root_cause_hypothesis") or "").strip(),
            reproduction_steps=_as_str_list(d.get("reproduction_steps")),
            technical_evidence=d.get("technical_evidence") if isinstance(d.get("technical_evidence"), dict) else {},
            affected_components=_as_str_list(d.get("affected_components")),
            status=str(d.get("status") or "completed"),
            error=str(d.get("error") or ""),
            evidence_ids=_as_str_list(d.get("evidence_ids")),
            input_status=d.get("input_status") if isinstance(d.get("input_status"), dict) else {},
        )

    def to_dict(self) -> dict:
        return {
            "issue_id": self.issue_id,
            "root_cause_hypothesis": self.root_cause_hypothesis,
            "reproduction_steps": list(self.reproduction_steps),
            "technical_evidence": dict(self.technical_evidence),
            "affected_components": list(self.affected_components),
            "status": self.status,
            "error": self.error,
            "evidence_ids": list(self.evidence_ids),
            "input_status": dict(self.input_status),
            "interpretation": "hypothesis",
        }


def parse_investigation(text: str, issue_id: str) -> Investigation:
    """解析 investigate 的 JSON 输出。失败抛 ValueError。"""
    data = loads_object(text)
    if not isinstance(data.get("root_cause_hypothesis"), str) or not data["root_cause_hypothesis"].strip():
        raise ValueError("调查输出缺少根因假设（无法确定时请明确说明）")
    fields = ("root_cause_hypothesis", "reproduction_steps", "technical_evidence", "affected_components")
    return Investigation.from_dict({key: data[key] for key in fields if key in data}, issue_id=issue_id)


def _as_str_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        items = []
    out = []
    for it in items:
        if isinstance(it, (str, int, float)) and str(it).strip():
            out.append(str(it).strip())
    return out
