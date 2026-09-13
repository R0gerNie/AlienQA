"""VisualObserver：视觉 LLM 描述变化 + 确定性白屏分。"""
import io

from ..llm import LLMClient, LlmRoles
from ..llm.jsonutil import loads_object
from .models import VisualObservation


class VisualObserver:
    def __init__(self, client: LLMClient):
        self.client = client
        self.roles = LlmRoles(client)

    def observe(self, before, after, action_desc: str) -> VisualObservation:
        vo = VisualObservation()
        if before is not None or after is not None:
            raw = self.roles.observe_visual(before, after, action_desc)
            try:
                vo = VisualObservation.from_dict(loads_object(raw))
            except (ValueError, TypeError):
                vo = VisualObservation()
        vo.blank_screen_score = blank_screen_score(after if after is not None else before)
        return vo


def blank_screen_score(image: bytes | None) -> float:
    """像素方差越低越接近白屏。返回 [0,1]：1=白屏，0=正常。"""
    if not image:
        return 0.0
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(image)).convert("L").resize((64, 64))
        pixels = list(im.tobytes())
    except Exception:  # noqa: BLE001 解码失败按正常页面处理
        return 0.0
    n = len(pixels)
    if n == 0:
        return 0.0
    mean = sum(pixels) / n
    variance = sum((p - mean) ** 2 for p in pixels) / n
    std = variance ** 0.5
    return max(0.0, min(1.0, 1.0 - std / 50.0))
