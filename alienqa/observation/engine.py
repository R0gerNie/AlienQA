"""ObservationEngine：合并视觉观察（LLM）与运行时观察（确定性）。"""
from ..llm import LLMClient
from ..driver.action import describe_visible_action
from .models import Observation
from .runtime_observer import RuntimeObserver
from .visual_observer import VisualObserver


class ObservationEngine:
    def __init__(self, client: LLMClient):
        self.visual = VisualObserver(client)
        self.runtime = RuntimeObserver()

    def observe(self, before, after, action, page, before_runtime=None) -> Observation:
        """before/after 为截图 bytes；action 为 Action；page 为 driver。"""
        runtime = self.observe_runtime(page, before_runtime)
        return self.observe_visual(before, after, action, page, runtime)

    def observe_runtime(self, page, before_runtime=None):
        return self.runtime.observe(page, before=before_runtime)

    def observe_visual(self, before, after, action, page, runtime) -> Observation:
        desc = _action_desc(action)
        visual = self.visual.observe(before, after, describe_visible_action(action), page_text=_page_text(page))
        return Observation(
            before_image=before,
            after_image=after,
            action_desc=desc,
            visual=visual,
            runtime=runtime,
        )


def _page_text(page) -> str:
    attr = getattr(page, "visible_text", "")
    if callable(attr):
        try:
            return attr() or ""
        except Exception:  # noqa: BLE001
            return ""
    return attr or ""


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
