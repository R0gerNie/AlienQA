"""Action Planner 测试：单元（评分/预算）+ 集成（探索循环）。"""
import pytest

from alienqa.driver import Action, PlaywrightDriver, Target
from alienqa.planner import ActionPlanner, Candidate, ExploreBudget, ExploreContext, explore, score
from alienqa.state import StateTracker

pytest.importorskip("playwright", reason="Playwright 未安装")


def _cand(text="", selector="#x", href="", tag="button"):
    return Candidate(
        action=Action("click", Target(text=text or None, selector=selector or None)),
        selector=selector,
        text=text,
        tag=tag,
        href=href,
    )


# ---- 单元：评分 ----

def test_boundary_scores_higher_than_normal():
    assert score(_cand("再次退款"), set(), set()) > score(_cand("编辑"), set(), set())


def test_risk_scores_higher_than_normal():
    assert score(_cand("删除订单"), set(), set()) > score(_cand("编辑"), set(), set())


def test_novelty_for_unexplored_link():
    link = _cand("前往后台", selector="#link", href="/admin", tag="a")
    normal = _cand("编辑", "#edit")
    assert score(link, set(), set()) > score(normal, set(), set())


# ---- 单元：Planner 核心 ----

def test_clicked_element_not_selected():
    p = ActionPlanner()
    p.clicked.add("#edit")
    chosen = p.plan(ExploreContext(), [_cand("编辑", "#edit")], None)
    assert chosen is None


def test_plan_picks_highest_score():
    p = ActionPlanner()
    cands = [_cand("编辑", "#edit"), _cand("再次退款", "#refund"), _cand("删除订单", "#del")]
    chosen = p.plan(ExploreContext(), cands, None)
    assert chosen.target.text in ("再次退款", "删除订单")


def test_should_stop_on_budget():
    p = ActionPlanner(budget=ExploreBudget(max_steps=3))
    p.steps = 3
    assert p.should_stop(0.0) is True
    p2 = ActionPlanner(budget=ExploreBudget(max_steps=10, max_time_seconds=1))
    assert p2.should_stop(2.0) is True


# ---- 集成：探索循环 ----

def test_explore_discovers_states_and_terminates(http_base_url):
    d = PlaywrightDriver()
    tracker = StateTracker()
    planner = ActionPlanner(budget=ExploreBudget(max_steps=10, max_time_seconds=60))
    d.launch(f"{http_base_url}/state-app/index.html")
    try:
        tracker = explore(d, tracker, planner)
        assert len(tracker.sequence()) >= 2
        assert planner.steps <= 10
    finally:
        d.close()


def test_explore_respects_step_budget(http_base_url):
    d = PlaywrightDriver()
    tracker = StateTracker()
    planner = ActionPlanner(budget=ExploreBudget(max_steps=2, max_time_seconds=60))
    d.launch(f"{http_base_url}/state-app/index.html")
    try:
        tracker = explore(d, tracker, planner)
        assert planner.steps <= 2
    finally:
        d.close()
