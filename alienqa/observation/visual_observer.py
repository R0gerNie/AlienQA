"""VisualObserver：视觉 LLM 描述变化 + 确定性白屏分。"""
import io

from ..llm import LLMClient, LlmRoles
from ..llm.jsonutil import loads_object
from .models import VisualObservation


class VisualObserver:
    def __init__(self, client: LLMClient):
        self.client = client
        self.roles = LlmRoles(client)

    def observe(self, before, after, action_desc: str, page_text: str = "") -> VisualObservation:
        vo = VisualObservation()
        if before is not None or after is not None:
            raw = self.roles.observe_visual(before, after, action_desc)
            try:
                vo = VisualObservation.from_dict(loads_object(raw))
            except (ValueError, TypeError):
                vo = VisualObservation()
        vo.blank_screen_score = blank_screen_score(after if after is not None else before, page_text)
        return vo


def blank_screen_score(image: bytes | None, visible_text: str = "") -> float:
    """白屏分：整页接近纯色**且无可见文字**→接近 1；有可见内容→0。返回 [0,1]。

    只靠像素方差会把"白底正常页"误判为白屏，所以叠加 visible_text 判定：
    页面只要有可见文字，就不是白屏（分数直接归 0）。
    """
    if not image:
        return 0.0
    if (visible_text or "").strip():
        return 0.0  # 有可见文字 → 白底正常页，不是白屏
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(image)).convert("L").resize((64, 64))
        pixels = list(im.tobytes())
    except Exception:  # noqa: BLE001
        return 0.0
    n = len(pixels)
    if n == 0:
        return 0.0
    mean = sum(pixels) / n
    variance = sum((p - mean) ** 2 for p in pixels) / n
    std = variance ** 0.5
    return max(0.0, min(1.0, 1.0 - std / 50.0))
