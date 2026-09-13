"""ActionPlanner：greedy 探索策略 + 端到端探索循环。"""
import time

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

    def extract_candidates(self, driver) -> list:
        """把 driver 枚举的可交互元素转成结构化 Candidate（过滤不可见/空元素）。"""
        candidates = []
        for el in driver.interactive_elements():
            if not el.get("visible", True):
                continue
            text = (el.get("text") or "").strip()
            selector = el.get("selector") or ""
            if not text and not selector:
                continue
            target = Target(text=text) if text else Target(selector=selector)
            candidates.append(Candidate(
                action=Action("click", target=target),
                selector=selector,
                text=text,
                tag=el.get("tag") or "",
                href=el.get("href") or "",
                role=el.get("role") or "",
            ))
        return candidates

    def plan(self, ctx: ExplorerContext, candidates, graph=None):
        """打分排序，返回最高分且未点击过的候选的 Action；无候选返回 None。"""
        if graph is not None:
            self.explored_routes = {n.route for n in graph.nodes}
        best = None
        best_score = float("-inf")
        for c in candidates:
            key = c.selector or c.text
            if key and key in self.clicked:
                continue
            s = score(c, self.clicked, self.explored_routes)
            if s > best_score:
                best = c
                best_score = s
        if best is None:
            return None
        key = best.selector or best.text
        if key:
            self.clicked.add(key)
        return best.action

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
    start = time.time()
    while True:
        if planner.should_stop(time.time() - start):
            break
        observation = Observation(screenshot=driver.screenshot(), visible_text=driver.visible_text())
        ctx = builder.build(
            product_map=product_map,
            state=state,
            observation=observation,
            history=tracker.sequence(),
        )
        candidates = planner.extract_candidates(driver)
        action = planner.plan(ctx, candidates, tracker.graph())
        if action is None:
            break
        planner.steps += 1
        try:
            state = tracker.capture(driver, action, timeout=1000)
        except Exception:
            # 点击失败（如被遮挡/元素消失）→ 跳过并继续，不中断探索
            continue
    return tracker
