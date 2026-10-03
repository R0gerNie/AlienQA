"""InvestigationAgent：对 Issue 做专家级调查（可看源码/DOM/技术信号）。"""
from alienqa.i18n import language_context, t as tr
from ..context.models import InvestigatorContext
from ..llm import LLMClient, LlmRoles
from .context import build_investigator_context
from .models import Investigation, parse_investigation


class InvestigationAgent:
    def __init__(self, client: LLMClient):
        self.client = client
        self.roles = LlmRoles(client)

    def investigate(self, issue, expert_ctx: InvestigatorContext) -> Investigation:
        with language_context(self.roles.language):
            return self._investigate(issue, expert_ctx)

    def _investigate(self, issue, expert_ctx: InvestigatorContext) -> Investigation:
        """契约入口：issue + 专家上下文 → Investigation。"""
        text = expert_ctx.to_text() if isinstance(expert_ctx, InvestigatorContext) else str(expert_ctx)
        issue_id = getattr(issue, "id", "") or ""
        text = tr("问题 {id}：{title}\n\n{text}", id=issue_id, title=getattr(issue, "title", ""), text=text)
        error = ""
        for repair in (False, True):
            try:
                raw = self.roles.investigate(text, repair=repair)
                result = parse_investigation(raw, issue_id)
                result.status, result.error = "completed", ""
                self.roles.mark_parse("succeeded")
                return result
            except Exception as exc:  # noqa: BLE001 调查失败也要显式记录，不能伪装为空结论。
                self.roles.mark_parse("failed", exc)
                error = str(exc)
                continue
        return Investigation(issue_id=issue_id, status="failed", error=error)

    def investigate_issue(self, project, issue, evidences, driver=None) -> Investigation:
        with language_context(self.roles.language):
            return self._investigate_issue(project, issue, evidences, driver)

    def _investigate_issue(self, project, issue, evidences, driver=None) -> Investigation:
        """便捷入口：先组装专家上下文再调查。"""
        try:
            ctx = build_investigator_context(project, issue, evidences, driver)
            result = self.investigate(issue, ctx)
            result.evidence_ids = list(issue.evidence_ids)
            result.input_status = ctx.input_status
            return result
        except Exception as exc:
            return Investigation(issue_id=issue.id, evidence_ids=list(issue.evidence_ids),
                                 status="failed", error=str(exc), input_status={"context": "failed"})
