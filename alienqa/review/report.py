"""ReportBuilder：人工采信项 → LLM 编排 HTML 报告（gate 拦截未审核/by-design/skipped）。"""
import json

from ..llm import LLMClient, LlmRoles
from .models import Decision, Report, ReviewState

# 报告基础样式：LLM 只产出 body 片段，这里包装成带 CSS 的可读 HTML 文档。
_REPORT_STYLE = """
<style>
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
         max-width: 920px; margin: 2rem auto; padding: 0 1rem;
         color: #1f2328; line-height: 1.6; }
  h1 { border-bottom: 2px solid #1f2328; padding-bottom: .4em; }
  h2 { margin-top: 1.6em; border-left: 4px solid #0969da; padding-left: .6em; }
  section { border: 1px solid #d0d7de; border-radius: 8px;
            padding: 1em 1.2em; margin: 1.2em 0; background: #fff; }
  table { border-collapse: collapse; width: 100%; margin: .5em 0; }
  th, td { border: 1px solid #d0d7de; padding: .45em .7em; text-align: left; vertical-align: top; }
  th { background: #f6f8fa; white-space: nowrap; }
  code { background: #f6f8fa; padding: .12em .35em; border-radius: 4px;
         font-family: ui-monospace, SFMono-Regular, monospace; font-size: .9em; }
  ol, ul { margin: .4em 0; padding-left: 1.7em; }
  hr { border: none; border-top: 1px dashed #d0d7de; margin: 1.5em 0; }
  small { color: #57606a; }
</style>
"""


def render_report_html(fragment: str) -> str:
    """把 LLM 产出的 body 片段包装成带样式的完整 HTML 文档。"""
    return (
        "<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
        "<title>AlienQA 疑似问题报告</title>"
        f"{_REPORT_STYLE}</head><body>"
        f"{fragment}</body></html>"
    )


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
        fragment = self.roles.compose_report(payload)
        return Report(
            html=render_report_html(fragment),
            accepted_count=len(accepted),
            total_count=len(evidences),
        )

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
