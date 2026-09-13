"""State Tracker 测试：单元 + 集成（对齐 planbook 第 8 节 6 条验收标准）。"""
import time

import pytest

from alienqa.state import StateTracker, normalize, signature

pytest.importorskip("playwright", reason="Playwright 未安装")

from alienqa.driver import Action, PlaywrightDriver, Target


# ---- 单元：签名与去噪 ----

def test_signature_stable_same_content():
    assert signature("/orders", "order list") == signature("/orders", "order list")


def test_signature_changes_route_or_text():
    assert signature("/orders", "hello") != signature("/login", "hello")
    assert signature("/orders", "hello") != signature("/orders", "world")


def test_normalize_strips_timestamp_and_id_keeps_digits():
    a = normalize("Order 2026-09-13 12:34:56 id-3f2a1b9c3f2a1b9c count: 5")
    b = normalize("Order 2026-09-14 08:00:00 id-9c7d0f9c7d0f9c7d count: 5")
    assert a == b
    assert "count: 5" in a


# ---- 单元：去重与图 ----

def test_observe_dedup_same_state():
    t = StateTracker()
    s1 = t.observe("/orders", "order list")
    s2 = t.observe("/orders", "order list")
    assert s1 is s2
    assert len(t.sequence()) == 1


def test_counter_increment_is_new_state():
    t = StateTracker()
    t.observe("/", "count: 0")
    assert t.is_new("/", "count: 1")


def test_graph_edges_parent_action_child():
    t = StateTracker()
    t.observe("/login", "login page")
    t.observe("/dashboard", "dashboard", action={"type": "click", "target": {"text": "Login"}})
    g = t.graph()
    assert len(g.nodes) == 2
    assert g.edges[0] == {
        "from": "S-001",
        "action": {"type": "click", "target": {"text": "Login"}},
        "to": "S-002",
    }


def test_save_load_roundtrip(tmp_path):
    t = StateTracker()
    t.observe("/", "home")
    t.observe("/orders", "orders", action={"type": "click"})
    p = tmp_path / "graph.json"
    t.save(p)
    t2 = StateTracker.load(p)
    assert t2.graph().to_dict() == t.graph().to_dict()


# ---- 集成：demo app ----

def test_demo_app_state_tracking(http_base_url):
    d = PlaywrightDriver()
    tracker = StateTracker()
    d.launch(f"{http_base_url}/state-app/index.html")
    try:
        tracker.capture(d)  # S-001 Home
        assert len(tracker.sequence()) == 1

        tracker.capture(d, Action("click", Target(selector=".tab[data-view='orders']")))  # S-002
        assert len(tracker.sequence()) == 2

        tracker.capture(d, Action("click", Target(selector=".tab[data-view='home']")))  # 回到 S-001
        assert len(tracker.sequence()) == 2

        tracker.capture(d, Action("click", Target(selector="#open-modal")))  # S-003
        assert len(tracker.sequence()) == 3

        tracker.capture(d, Action("click", Target(selector="#close-modal")))  # 回到 S-001
        assert len(tracker.sequence()) == 3

        tracker.capture(d, Action("click", Target(selector="#count-up")))  # S-004（数字变化）
        assert len(tracker.sequence()) == 4
    finally:
        d.close()


def test_clock_tick_is_not_new_state(http_base_url):
    d = PlaywrightDriver()
    tracker = StateTracker()
    d.launch(f"{http_base_url}/state-app/index.html")
    try:
        tracker.capture(d)
        time.sleep(1.2)  # 让时钟走一秒
        tracker.capture(d)
        assert len(tracker.sequence()) == 1  # 时间戳被去噪
    finally:
        d.close()
