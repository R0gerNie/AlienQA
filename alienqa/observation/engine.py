"""ObservationEngine：合并视觉观察（LLM）与运行时观察（确定性）。"""
from ..llm import LLMClient
from .models import Observation
from .runtime_observer import RuntimeObserver
from .visual_observer import VisualObserver


class ObservationEngine:
    def __init__(self, client: LLMClient):
        self.visual = VisualObserver(client)
        self.runtime = RuntimeObserver()

    def observe(self, before, after, action, page, before_runtime=None) -> Observation:
        """before/after 为截图 bytes；action 为 Action；page 为 driver。"""
        desc = _action_desc(action)
        visual = self.visual.observe(before, after, desc)
        runtime = self.runtime.observe(page, before=before_runtime)
        return Observation(
            before_image=before,
            after_image=after,
            action_desc=desc,
            visual=visual,
            runtime=runtime,
        )


def _action_desc(action) -> str:
    if action is None:
        return ""
    if hasattr(action, "type"):
        target = getattr(action, "target", None)
        label = ""
        if target is not None:
            label = getattr(target, "text", "") or getattr(target, "selector", "") or ""
        return " ".join(x for x in (str(getattr(action, "type", "")), str(label)) if x).strip()
    if isinstance(action, dict):
        t = action.get("type") or action.get("action") or ""
        target = action.get("target") or {}
        label = ""
        if isinstance(target, dict):
            label = target.get("text") or target.get("selector") or ""
        else:
            label = str(target)
        return " ".join(x for x in (str(t), str(label)) if x).strip()
    return str(action)
