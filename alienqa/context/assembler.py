"""ExplorationContext：认知防火墙——单一出口，白名单裁剪，组装 ExplorerContext。

任何模块不得绕过本模块直接向 Explorer 塞信息；06 / 08 只消费 ExplorerContext。
"""
from .models import ExplorerContext, ScreenshotProcessor
from .policy import ContextPolicy
from alienqa.driver.runtime import clean_message
from alienqa.driver.action import describe_visible_action


class ExplorationContext:
    def __init__(
        self,
        policy: ContextPolicy | None = None,
        screenshot_processor: ScreenshotProcessor | None = None,
    ):
        self.policy = policy or ContextPolicy()
        self.screenshot_processor = screenshot_processor or ScreenshotProcessor()

    def is_allowed(self, field: str) -> bool:
        return self.policy.is_allowed(field)

    def build(self, product_map, state, observation, history) -> ExplorerContext:
        """只从各输入里裁剪白名单字段，组装 ExplorerContext。"""
        ctx = ExplorerContext()
        ctx.state_id = getattr(state, "id", "") if state is not None else ""
        if self.is_allowed("visible_text"):
            visible = clean_message(_visible_text(state, observation))
            ctx.visible_text = visible[:4000]
            ctx.input_limits["visible_text_truncated"] = len(visible) > 4000
        if self.is_allowed("product_brief"):
            ctx.product_brief = ctx.visible_text[:1000]
        # Source-derived map edges/brief are locator inputs, never user priors.
        if self.is_allowed("action_history"):
            completed = [s for s in history or [] if isinstance(s, dict)
                         and s.get("execution_status") == "completed"
                         and isinstance(s.get("visible_result"), str) and s.get("step_id")]
            ctx.visible_history = [{"step_id": s["step_id"], "action": describe_visible_action(s.get("action")),
                                    "visible_result": clean_message(s["visible_result"])[:1000],
                                    "result_truncated": len(s["visible_result"]) > 1000}
                                   for s in completed[-5:]]
            ctx.input_limits["history_truncated"] = len(completed) > 5
            legacy = [s for s in history or [] if not isinstance(s, dict) or "execution_status" not in s]
            ctx.action_history = [s["action"] for s in ctx.visible_history] if completed else _history(legacy)[-5:]
        if self.is_allowed("screenshot"):
            ctx.screenshot = self.screenshot_processor.process(_screenshot(observation))
        ctx.forbidden = {f: False for f in self.policy.forbidden}
        return ctx


# ---- 输入适配器（只取白名单字段，多的一律不碰） ----

def _visible_text(state, observation) -> str:
    if observation is not None and getattr(observation, "visible_text", ""):
        return observation.visible_text
    if state is not None:
        return getattr(state, "snapshot", "") or ""
    return ""


def _screenshot(observation) -> bytes | None:
    if observation is None:
        return None
    return getattr(observation, "screenshot", None)


def _describe_action(action) -> str:
    if action is None:
        return ""
    if isinstance(action, dict):
        if "state_id" in action and "action" in action:
            return _describe_action(action["action"])
        act_type = action.get("type") or action.get("action") or ""
        target = action.get("target") or {}
        if isinstance(target, dict):
            label = target.get("text") or target.get("selector") or ""
        else:
            label = str(target)
        return " ".join(x for x in (str(act_type), str(label)) if x).strip()[:200]
    return str(action)


def _history(history) -> list:
    out = []
    for item in history or []:
        if hasattr(item, "action"):  # State
            desc = _describe_action(item.action)
        elif isinstance(item, (dict, str)):
            desc = _describe_action(item)
        else:
            desc = ""
        if desc:
            out.append(desc)
    return out
