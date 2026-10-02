"""ActionPlanner：greedy 探索策略 + 端到端探索循环。"""
import time
import math
import re

from alienqa.context import ExplorationContext, ExplorerContext, Observation
from alienqa.driver import Action, Target

from .models import Candidate, ExploreBudget
from .scorer import score


class ActionPlanner:
    def __init__(self, budget: ExploreBudget | None = None):
        self.budget = budget or ExploreBudget()
        self.clicked: set = set()
        self.explored_routes: set = set()
        self.steps = 0
        self._completed: set = set()
        self._failures: dict = {}
        self.input_diagnostics: list = []
        self._uncertain: set = set()
        self._input_branches: set = set()
        self._route = ""
        self._opened_popups: set = set()

    def extract_candidates(self, driver) -> list:
        """把 driver 枚举的可交互元素转成结构化 Candidate（过滤不可见/空元素）。"""
        candidates = []
        self.input_diagnostics = []
        self._route = driver.url() if hasattr(driver, "url") else ""
        for el in driver.interactive_elements():
            if not el.get("visible", True) or el.get("disabled") or el.get("readonly"):
                continue
            text = (el.get("text") or "").strip()
            selector = el.get("selector") or ""
            if not text and not selector:
                continue
            tag = el.get("tag") or ""
            input_type = el.get("input_type") or "text"
            text = text or el.get("name") or el.get("label") or el.get("placeholder") or ""
            target = Target(selector=selector or None, text=text or None,
                            role=el.get("role") or None, name=el.get("name") or None,
                            label=el.get("label") or None, scope=el.get("scope") or None,
                            visible=el.get("visible_identity"))
            actions = []
            if el.get("dismiss_surface"):
                actions.append(Action("press", target, "Escape"))
            elif tag in {"input", "textarea"} or el.get("contenteditable"):
                if input_type in {"hidden", "file", "reset", "image"}:
                    continue
                if input_type in {"checkbox", "radio"}:
                    if not el.get("checked") and not (input_type == "radio" and el.get("group_checked")):
                        actions.append(Action("click", target))
                elif input_type in {"button", "submit"}:
                    actions.append(Action("click", target))
                else:
                    if _json_input(el):
                        value = _sample_value(el)
                        if el.get("focused"):
                            actions.append(Action("blur", target))
                        if value is not None:
                            for branch, sample in (("valid", value), ("invalid", "not valid JSON"), ("empty", "")):
                                if branch != "empty" and el.get("maxlength") is not None and len(sample) > int(el["maxlength"]):
                                    continue
                                actions.append(Action("type", target, sample, input_branch=branch))
                        else:
                            self.input_diagnostics.append({"label": text, "status": "unverified",
                                                           "reason": "可见约束不支持 JSON 样本，未绕过约束"})
                    elif not el.get("value"):
                        value = _sample_value(el)
                        if value is not None:
                            actions.append(Action("type", target, value))
                        else:
                            self.input_diagnostics.append({"label": text, "status": "unverified",
                                                           "reason": "无法根据可见输入约束构造合法样本，未提交该字段"})
                    elif el.get("focused"):
                        actions.append(Action("blur", target))
                    elif input_type == "search" or el.get("implicit_submit") or (
                        tag == "input" and input_type == "text"
                        and not el.get("form_key") and not el.get("contenteditable")
                    ):
                        # Formless single-line widgets may submit with Enter.
                        # Probe observable behavior; this does not assume success.
                        actions.append(Action("press", target, "Enter"))
            elif tag == "select":
                options = el.get("options") or []
                has_value = bool(el.get("value")) or any(o.get("selected") and o.get("value") for o in options)
                if not has_value:
                    for option in options:
                        if option.get("value") and not option.get("disabled") and not option.get("selected"):
                            actions.append(Action("select", target, str(option["value"])))
                            break
            else:
                if el.get("role") in {"option", "tab"} and el.get("selected"):
                    continue
                if el.get("role") in {"checkbox", "radio", "switch"} and el.get("checked"):
                    continue
                actions.append(Action("click", target))
            if el.get("hover_hint"):
                actions.append(Action("hover", target))
            for action in actions:
                candidates.append(Candidate(
                    action=action, selector=selector, text=text, tag=tag,
                    href=el.get("href") or "", role=el.get("role") or "",
                    form_key=el.get("form_key") or "", input_type=input_type,
                    form_preparation=action.type in {"type", "select", "blur"} or (
                        input_type in {"checkbox", "radio"} and bool(el.get("required"))
                    ),
                    popup_owners=el.get("popup_owners", []),
                ))
        return candidates

    def plan(self, ctx: ExplorerContext, candidates, graph=None):
        """选择当前状态尚未成功探索的动作；执行结果由 record_result 提交。"""
        if graph is not None:
            self.explored_routes = {n.route for n in graph.nodes}
        best = None
        best_score = float("-inf")
        state_id = getattr(ctx, "state_id", "")
        available = [c for c in candidates if self._available(c.action, state_id)]
        pending_forms = {c.form_key for c in available
                         if c.form_key and c.action.input_branch not in {"invalid", "empty"}
                         and (c.form_preparation or c.action.type in {"type", "select"})}
        for c in available:
            key = c.selector or c.text
            # Legacy callers may seed clicked directly; completed actions are state-local.
            if not state_id and key and key in self.clicked:
                continue
            if c.form_key in pending_forms and c.action.type in {"click", "press"}:
                if c.input_type == "submit" or c.action.type == "press":
                    continue
            s = score(c, set(), self.explored_routes)
            if c.action.type == "click" and (c.action.target.visible or {}).get("expanded") is False and self._control_key(c.action) in self._opened_popups:
                s -= 10.0  # finish remaining work before revisiting a popup in a changed state
            if c.form_preparation or c.action.type in {"type", "select"}:
                s += 20.0
                if c.form_key and c.action.input_branch in {"invalid", "empty"}:
                    s -= 30.0  # observe a valid submit before probing alternative inputs
            elif c.action.type == "press":
                s += -100.0 if c.action.text == "Escape" else 2.0
            elif c.action.type == "hover":
                s -= 1.0
            if s > best_score:
                best = c
                best_score = s
        if best is None:
            return None
        return best.action

    @staticmethod
    def _key(action: Action, state_id: str) -> tuple:
        target = action.target
        location = (target.scope, target.selector or target.name or target.label or target.text or target.role or (target.x, target.y))
        return state_id, action.type, location, action.text

    def _available(self, action: Action, state_id: str) -> bool:
        key = self._key(action, state_id)
        if action.input_branch and self._input_key(action) in self._input_branches:
            return False
        return key not in self._completed and key not in self._uncertain and self._failures.get(key, 0) < self.budget.max_failures_per_action

    def _input_key(self, action):
        return self._route, self._key(action, "")[2], action.input_branch

    def _control_key(self, action):
        return self._route, self._key(action, "")[2]

    def record_uncertain(self, action: Action, state_id: str) -> None:
        """An unknown emission cannot safely be retried as a known failed click."""
        self._uncertain.add(self._key(action, state_id))

    def record_result(self, action: Action, state_id: str, success: bool) -> None:
        """成功动作不重复；失败允许有限重试，不冒充成功覆盖。"""
        key = self._key(action, state_id)
        if success:
            self._completed.add(key)
            if action.input_branch:
                self._input_branches.add(self._input_key(action))
            if action.type == "click" and (action.target.visible or {}).get("popup"):
                self._opened_popups.add(self._control_key(action))
            self._failures.pop(key, None)
        else:
            self._failures[key] = self._failures.get(key, 0) + 1

    def should_stop(self, elapsed: float) -> bool:
        return self.steps >= self.budget.max_steps or elapsed >= self.budget.max_time_seconds


def explore(driver, tracker, planner: ActionPlanner, budget: ExploreBudget | None = None,
            product_map=None, context_builder: ExplorationContext | None = None):
    """端到端探索循环：把 04 + 05 + 06 串起来。

    Explorer 上下文一律经 03 认知防火墙组装（单一出口），不直接读 driver。
    """
    if budget is not None:
        planner.budget = budget
    builder = context_builder or ExplorationContext()
    state = tracker.capture(driver)
    start = time.monotonic()
    if hasattr(driver, "set_deadline"):
        driver.set_deadline(start + planner.budget.max_time_seconds)
    while True:
        if planner.should_stop(time.monotonic() - start):
            break
        observation = Observation(screenshot=driver.screenshot(), visible_text=driver.visible_text())
        ctx = builder.build(
            product_map=product_map,
            state=state,
            observation=observation,
            history=tracker.trajectory(),
        )
        candidates = planner.extract_candidates(driver)
        action = planner.plan(ctx, candidates, tracker.graph())
        if action is None:
            break
        planner.steps += 1
        previous_state_id = state.id
        try:
            state = tracker.capture(driver, action, timeout=3000, step_id=f"ST-{planner.steps:05d}")
            execution = getattr(driver, "last_execution", {})
            planner.record_result(action, previous_state_id, execution.get("status", "completed") == "completed")
        except Exception:
            # 点击失败（如被遮挡/元素消失）→ 跳过并继续，不中断探索
            planner.record_result(action, previous_state_id, False)
            result = getattr(driver, "last_execution", {})
            if "emitted" in result and result["emitted"] is None:
                planner.record_uncertain(action, previous_state_id)
            continue
    return tracker


def _sample_value(element: dict) -> str | None:
    """Deterministic valid-looking inputs make exploration and replay reproducible."""
    kind = element.get("input_type") or "text"
    values = {
        "email": "alienqa@example.com", "password": "AlienQA123!",
        "tel": "13800138000", "url": "https://example.com", "number": "1",
        "date": "2026-01-01", "time": "12:00", "datetime-local": "2026-01-01T12:00",
        "month": "2026-01", "week": "2026-W01", "range": "50", "color": "#336699",
    }
    semantic_json = _json_input(element)
    value = '{"name":"AlienQA","count":2}' if semantic_json else values.get(kind, "AlienQA test")
    if kind in {"number", "range"}:
        try:
            low = float(element.get("min") or (0 if kind == "range" else "-inf"))
            high = float(element.get("max") or (100 if kind == "range" else "inf"))
            if low > high:
                return None
            value = str(max(low, min(high, float(value))))
            step = element.get("step")
            if step and step != "any":
                increment = float(step)
                if increment <= 0 or not math.isfinite(increment):
                    return None
                base = low if math.isfinite(low) else 0
                aligned = base + math.floor((float(value)-base)/increment)*increment
                if aligned < low:
                    aligned += increment
                if aligned > high or not math.isfinite(aligned):
                    return None
                value = str(aligned)
        except ValueError:
            return None
    if kind in {"date", "time", "datetime-local", "month", "week"}:
        value = str(element.get("min") or value)
        if element.get("max") and value > element["max"]:
            value = str(element["max"])
        if element.get("min") and element.get("max") and element["min"] > element["max"]:
            return None
    maxlength = element.get("maxlength")
    if maxlength is not None and int(maxlength) > 0:
        if semantic_json and len(value) > int(maxlength):
            return None
        if len(value) > int(maxlength) and kind in {"email", "url"}:
            value = "a@b.co" if kind == "email" else "https://a.co"
            if len(value) > int(maxlength):
                return None
        elif kind in {"number", "range", "date", "time", "datetime-local", "month", "week", "color"}:
            return value
        else:
            value = value[:int(maxlength)]
    # Pattern business formats cannot safely be invented; retain a diagnostic.
    if element.get("pattern"):
        return None
    return value


def _json_input(element):
    if element.get("input_type", "text") not in {"text", "search", "textarea"}:
        return False
    # Only user-visible labels/placeholder, never field IDs or framework implementation.
    label = " ".join(str(element.get(key) or "") for key in ("text", "name", "label", "placeholder"))
    return bool(re.search(r"\bjson\b", label, re.I))
