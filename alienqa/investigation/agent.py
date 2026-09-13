"""InvestigationAgent：对 Issue 做专家级调查（可看源码/DOM/技术信号）。"""
from ..context.models import InvestigatorContext
from ..llm import LLMClient, LlmRoles
from .context import build_investigator_context
from .models import Investigation, parse_investigation


class InvestigationAgent:
    def __init__(self, client: LLMClient):
        self.client = client
        self.roles = LlmRoles(client)

    def investigate(self, issue, expert_ctx: InvestigatorContext) -> Investigation:
        """契约入口：issue + 专家上下文 → Investigation。"""
        text = expert_ctx.to_text() if isinstance(expert_ctx, InvestigatorContext) else str(expert_ctx)
        issue_id = getattr(issue, "id", "") or ""
        for repair in (False, True):
            raw = self.roles.investigate(text, repair=repair)
            try:
                return parse_investigation(raw, issue_id)
            except (ValueError, TypeError):
                continue
        return Investigation(issue_id=issue_id)

    def investigate_issue(self, project, issue, evidences, driver=None) -> Investigation:
        """便捷入口：先组装专家上下文再调查。"""
        ctx = build_investigator_context(project, issue, evidences, driver)
        return self.investigate(issue, ctx)
