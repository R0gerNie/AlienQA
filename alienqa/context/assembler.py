"""ExplorationContext：认知防火墙——单一出口，白名单裁剪，组装 ExplorerContext。

任何模块不得绕过本模块直接向 Explorer 塞信息；06 / 08 只消费 ExplorerContext。
"""
from .models import ExplorerContext, ScreenshotProcessor
from .policy import ContextPolicy


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
        if self.is_allowed("product_brief"):
            ctx.product_brief = _brief(product_map)
        if self.is_allowed("visible_text"):
            ctx.visible_text = _visible_text(state, observation)
        if self.is_allowed("navigation"):
            ctx.navigation = _navigation(product_map, state)
        if self.is_allowed("action_history"):
            ctx.action_history = _history(history)
        if self.is_allowed("screenshot"):
            ctx.screenshot = self.screenshot_processor.process(_screenshot(observation))
        ctx.forbidden = {f: False for f in self.policy.forbidden}
        return ctx


# ---- 输入适配器（只取白名单字段，多的一律不碰） ----

def _brief(product_map) -> str:
    if product_map is None:
        return ""
    return getattr(product_map, "brief", "") or ""


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


def _navigation(product_map, state) -> list:
    if product_map is None or state is None:
        return []
    route = getattr(state, "route", "") or ""
    out = []
    for rel in getattr(product_map, "relations", []) or []:
        src = getattr(rel, "from_", None)
        if src is None:
            src = getattr(rel, "from", "")
        if src == route:
            out.append({"from": route, "to": getattr(rel, "to", ""), "kind": getattr(rel, "kind", "navigate")})
    return out


def _describe_action(action) -> str:
    if action is None:
        return ""
    if isinstance(action, dict):
        act_type = action.get("type") or action.get("action") or ""
        target = action.get("target") or {}
        if isinstance(target, dict):
            label = target.get("text") or target.get("selector") or ""
        else:
            label = str(target)
        return " ".join(x for x in (str(act_type), str(label)) if x).strip()
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
