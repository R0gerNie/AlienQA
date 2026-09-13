"""ExpectationEngine：基于陌生用户直觉生成预期，并与观察比对产出 Mismatch。

先观察后预期解耦：expect() 不读 Observation，judge() 才读。
"""
from ..context.models import ExplorerContext
from ..llm import LLMClient, LlmRoles
from .models import Expectation, ExpectationMismatch, Observation, PageInfo, parse_mismatch


class ExpectationEngine:
    def __init__(self, client: LLMClient, samples: int = 2):
        self.client = client
        self.roles = LlmRoles(client)
        self.samples = samples

    def expect(self, ctx: ExplorerContext, page_info: PageInfo) -> list:
        """生成预期（不读 Observation，防自我确认）。"""
        page_text = _compose_page_text(ctx, page_info)
        texts = self.roles.generate_expectations(
            gist=getattr(ctx, "product_brief", "") or "",
            page_text=page_text,
            samples=self.samples,
        )
        return [Expectation(text=t) for t in texts]

    def judge(self, expectations, observation) -> ExpectationMismatch | None:
        """逐条预期比对观察，返回最严重 mismatch；全匹配或不可判定返回 None。"""
        expected_texts = [getattr(e, "text", "") for e in expectations if getattr(e, "text", "")]
        if not expected_texts:
            return None
        obs = _coerce_observation(observation)
        if obs is None:
            return None
        expected = "\n".join(f"- {t}" for t in expected_texts)
        for repair in (False, True):
            raw = self.roles.judge(
                getattr(obs, "action_desc", "") or "",
                expected,
                getattr(obs, "before_image", None),
                getattr(obs, "after_image", None),
                technical=getattr(obs, "technical", None) or {},
                repair=repair,
            )
            try:
                return parse_mismatch(raw)
            except (ValueError, TypeError):
                continue
        return None


def _compose_page_text(ctx, page_info) -> str:
    parts = []
    if page_info is not None and getattr(page_info, "route", ""):
        parts.append(f"当前页面: {page_info.route}")
    if page_info is not None and getattr(page_info, "elements", None):
        parts.append("可见元素:\n" + "\n".join(f"- {e}" for e in page_info.elements))
    text = getattr(ctx, "visible_text", "") or ""
    if text:
        parts.append(f"页面文字:\n{text[:4000]}")
    return "\n\n".join(parts)


def _coerce_observation(observation) -> Observation | None:
    """07 的 canonical Observation（或任何带 before_image/after_image/action_desc/technical 的对象）。"""
    if observation is None:
        return None
    return observation
