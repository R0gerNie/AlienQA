"""Exploration regressions: state-local coverage, real forms, and replay provenance."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alienqa.context import ExplorationContext, Observation
from alienqa.driver import Action, PlaywrightDriver, Target
from alienqa.mapper import ProductMap, Relation
from alienqa.planner import ActionPlanner, Candidate, ExploreBudget, explore, score
from alienqa.state import StateTracker


def _candidate(action_type="click", text="", selector="#save"):
    return Candidate(Action(action_type, Target(selector=selector), text), selector=selector)


def test_plan_commits_only_success_and_is_scoped_to_state_and_action():
    planner = ActionPlanner()
    ctx = SimpleNamespace(state_id="S-1")
    candidate = _candidate()
    assert planner.plan(ctx, [candidate]) is candidate.action
    assert planner.plan(ctx, [candidate]) is candidate.action
    planner.record_result(candidate.action, ctx.state_id, True)
    assert planner.plan(ctx, [candidate]) is None
    assert planner.plan(SimpleNamespace(state_id="S-2"), [candidate]) is candidate.action
    hover = _candidate("hover")
    assert planner.plan(ctx, [hover]) is hover.action


def test_failed_action_retries_then_exhausts_without_blocking_other_candidates():
    planner = ActionPlanner()
    ctx = SimpleNamespace(state_id="S-1")
    candidate = _candidate()
    for _ in range(2):
        assert planner.plan(ctx, [candidate]) is candidate.action
        planner.record_result(candidate.action, ctx.state_id, False)
    assert planner.plan(ctx, [candidate]) is None
    other = _candidate(selector="#other")
    assert planner.plan(ctx, [candidate, other]) is other.action


def test_extracts_form_actions_and_fills_before_submit():
    driver = SimpleNamespace(interactive_elements=lambda: [
        {"selector": "#email", "tag": "input", "input_type": "email", "form_key": "#form", "value": ""},
        {"selector": "#country", "tag": "select", "form_key": "#form", "options": [
            {"value": "", "label": "Choose", "selected": True},
            {"value": "cn", "label": "China"},
        ]},
        {"selector": "#submit", "tag": "button", "text": "Submit", "input_type": "submit", "form_key": "#form"},
        {"selector": "#menu", "tag": "button", "text": "Menu", "hover_hint": True},
        {"selector": "#search", "tag": "input", "input_type": "search", "value": "query"},
        {"selector": "#disabled", "tag": "input", "disabled": True},
        {"selector": "#file", "tag": "input", "input_type": "file"},
    ])
    planner = ActionPlanner()
    candidates = planner.extract_candidates(driver)
    assert {c.action.type for c in candidates} == {"click", "type", "select", "hover", "press"}
    assert next(c.action.text for c in candidates if c.action.type == "type") == "alienqa@example.com"
    assert next(c.action.text for c in candidates if c.action.type == "select") == "cn"
    assert all(c.selector not in {"#disabled", "#file"} for c in candidates)
    ctx = SimpleNamespace(state_id="S-1")
    first = planner.plan(ctx, candidates)
    assert first.type in {"type", "select"}
    planner.record_result(first, ctx.state_id, True)
    second = planner.plan(ctx, candidates)
    assert second.type in {"type", "select"} and second is not first


def test_required_check_precedes_submit_and_selected_value_stops_preparation():
    driver = SimpleNamespace(interactive_elements=lambda: [
        {"selector": "#submit", "tag": "button", "input_type": "submit", "form_key": "#form"},
        {"selector": "#terms", "tag": "input", "input_type": "checkbox", "required": True, "form_key": "#form"},
        {"selector": "#country", "tag": "select", "value": "cn", "form_key": "#form", "options": [
            {"value": "cn", "selected": True}, {"value": "us"},
        ]},
        {"selector": "#radio", "tag": "input", "input_type": "radio", "required": True,
         "form_key": "#form", "group_checked": True},
    ])
    planner = ActionPlanner()
    candidates = planner.extract_candidates(driver)
    assert [c.selector for c in candidates] == ["#submit", "#terms"]
    assert planner.plan(SimpleNamespace(state_id="S-1"), candidates).target.selector == "#terms"


def test_field_state_changes_signature_without_exposing_values_in_state():
    tracker = StateTracker()
    first = tracker.observe("/", "Form", form_state=[{"key": "email", "value": ""}])
    second = tracker.observe("/", "Form", form_state=[{"key": "email", "value": "secret@example.com"}])
    assert first.id != second.id
    assert tracker.observe("/", "Form", form_state=[{"value": "", "key": "email"}]) is first
    assert "secret@example.com" not in str(tracker.graph().to_dict())


def test_navigation_novelty_compares_paths_with_absolute_routes():
    link = Candidate(Action("click", Target(selector="#link")), selector="#link", href="/orders/", tag="a")
    assert score(link, set(), {"http://localhost:123/orders"}) == score(link, set(), {"/orders/"})


def test_return_edges_and_action_history_survive_save_load(tmp_path):
    tracker = StateTracker()
    first = tracker.observe("/", "Home")
    tracker.observe("/orders", "Orders", Action("click", Target(selector="#orders")))
    tracker.observe("/", "Home", Action("click", Target(selector="#home")))
    tracker.observe("/", "Home", Action("hover", Target(selector="#menu")))
    assert len(tracker.sequence()) == 2
    assert [(e["from"], e["to"]) for e in tracker.graph().edges] == [
        (first.id, "S-002"), ("S-002", first.id), (first.id, first.id),
    ]
    assert [a["type"] for a in tracker.action_history()] == ["click", "click", "hover"]
    path = tmp_path / "graph.json"
    tracker.save(path)
    loaded = StateTracker.load(path)
    assert loaded.action_history() == tracker.action_history()
    loaded.observe("/other", "Other", Action("click", Target(selector="#other")))
    assert loaded.graph().edges[-1]["from"] == first.id


def test_context_exposes_state_id_and_matches_absolute_url_navigation():
    tracker = StateTracker()
    state = tracker.observe("http://localhost:123/orders/", "Orders")
    tracker.observe(state.route, state.snapshot, Action("type", Target(selector="#name"), "Alice"))
    context = ExplorationContext().build(
        ProductMap(relations=[Relation(from_="/orders", to="/account")]),
        state, Observation(), tracker.action_history(),
    )
    assert context.state_id == state.id
    assert context.navigation == []
    assert context.action_history == ["type #name"]


def test_driver_records_only_successful_actions_and_accepts_coordinate_only_target():
    driver = PlaywrightDriver()
    driver._page = Mock()
    driver.wait_for_settle = Mock()
    driver._page.locator.return_value.click.side_effect = RuntimeError("not clickable")
    with pytest.raises(RuntimeError):
        driver.execute(Action("click", Target(selector="#missing")))
    assert driver.replay_data()["action_sequence"] == []
    driver.execute(Action("click", Target(x=10, y=20)))
    driver._page.mouse.click.assert_called_once_with(10, 20)
    assert len(driver.replay_data()["action_sequence"]) == 1


def test_driver_selects_by_option_value():
    driver = PlaywrightDriver()
    driver._page = Mock()
    driver.wait_for_settle = Mock()
    driver.execute(Action("select", Target(selector="#country"), "cn"))
    call = driver._page.locator.return_value.select_option
    call.assert_called_once()
    assert call.call_args.kwargs["value"] == "cn"
    assert 0 < call.call_args.kwargs["timeout"] <= 3000


def test_explore_retries_failed_execution_and_preserves_success_history():
    class Driver:
        attempts = 0

        def interactive_elements(self):
            return [{"selector": "#save", "tag": "button", "text": "Save"}]

        def url(self):
            return "/"

        def visible_text(self):
            return "Home"

        def screenshot(self):
            return b""

        def execute(self, action, timeout=3000):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("transient")

    driver = Driver()
    tracker = explore(driver, StateTracker(), ActionPlanner(ExploreBudget(max_steps=5)))
    assert driver.attempts == 2
    assert len(tracker.action_history()) == 1


def test_real_form_exploration_and_replay_start_url(http_base_url):
    pytest.importorskip("playwright")
    driver = PlaywrightDriver()
    url = f"{http_base_url}/form-app/index.html"
    driver.launch(url)
    try:
        tracker = explore(driver, StateTracker(), ActionPlanner(ExploreBudget(max_steps=12)))
        assert "Submitted alienqa@example.com / cn" in driver.visible_text()
        data = driver.replay_data()
        assert data["url"] == url
        assert data["final_url"].endswith("#submitted")
        assert data["storage_state"]["origins"][0]["localStorage"] == [{"name": "seed", "value": "initial"}]
        assert [a["type"] for a in data["action_sequence"]][:4] == ["type", "blur", "select", "click"]
        assert len(tracker.action_history()) >= 3
    finally:
        driver.close()


def test_real_required_checkbox_and_select_submit_with_finite_budget(http_base_url):
    pytest.importorskip("playwright")
    driver = PlaywrightDriver(browser="chromium")
    driver.launch(f"{http_base_url}/form-app/required-form.html")
    try:
        planner = ActionPlanner(ExploreBudget(max_steps=3))
        tracker = explore(driver, StateTracker(), planner)
        assert "Submitted cn / accepted" in driver.visible_text()
        assert [a["type"] for a in tracker.action_history()] == ["select", "click", "click"]
        assert [a["target"]["selector"] for a in tracker.action_history()][-2:] == ["#terms", "#submit"]
        assert len(tracker.sequence()) == 4
    finally:
        driver.close()
