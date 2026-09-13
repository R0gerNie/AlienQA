"""ReportBuilder：人工采信项 → LLM 编排 HTML 报告（gate 拦截未审核/by-design/skipped）。"""
import json

from ..llm import LLMClient, LlmRoles
from .models import Decision, Report, ReviewState


class ReportBuilder:
    def __init__(self, client: LLMClient):
        self.client = client
        self.roles = LlmRoles(client)

    def build(self, evidences, state: ReviewState, investigations=None) -> Report:
        self._validate(evidences, state)
        accepted = [e for e in evidences if state.decision(e.id) == Decision.CONFIRMED]
        inv_map = {inv.issue_id: inv for inv in (investigations or []) if getattr(inv, "issue_id", "")}
        payload = json.dumps(
            [_evidence_dict(e, inv_map.get(e.issue_id)) for e in accepted],
            ensure_ascii=False,
            indent=2,
        )
        html = self.roles.compose_report(payload)
        return Report(html=html, accepted_count=len(accepted), total_count=len(evidences))

    def _validate(self, evidences, state: ReviewState) -> None:
        for e in evidences:
            d = state.decision(e.id)
            if d in (Decision.BY_DESIGN, Decision.SKIPPED):
                raise ValueError(f"证据 {e.id} 仍处于 {d.value} 状态，报告生成前必须清空 by-design/skipped")
            if d is Decision.PENDING:
                raise ValueError(f"证据 {e.id} 尚未审核，不能生成报告")


def _evidence_dict(e, investigation=None) -> dict:
    repro = _repro(e)
    root_cause = ""
    if investigation is not None:
        repro = list(investigation.reproduction_steps) or repro
        root_cause = investigation.root_cause_hypothesis
    return {
        "id": e.id,
        "severity": e.severity.value,
        "expectation": e.expectation,
        "observation": e.observation_summary,
        "reasoning": e.reasoning,
        "classification": e.classification,
        "reproduction": repro,
        "root_cause": root_cause,
    }


def _repro(e) -> list:
    seq = (e.replay or {}).get("action_sequence") or []
    out = []
    for a in seq:
        if isinstance(a, dict):
            target = a.get("target") or {}
            label = (target.get("text") or target.get("selector") or "") if isinstance(target, dict) else str(target)
            out.append(f"{a.get('type', '')} {label}".strip())
        else:
            out.append(str(a))
    return [x for x in out if x]
