"""Regressions from the first frozen real-model batch; no model calls here."""
from types import SimpleNamespace

import pytest

from alienqa.context import ExplorerContext
from alienqa.expectation.contracts import merge_samples
from alienqa.planner import ActionPlanner, ExploreBudget, explore
from alienqa.state import StateTracker


TYPE_PAIR = (
    "在「New Todo Input」中输入文本后，输入框应可见地显示所输入的内容。",
    "在「New Todo Input」中输入文字后，输入框应可见地显示所输入的内容。",
)
BLUR_PAIR = (
    "New Todo Input 失去焦点，不再显示输入光标。",
    "New Todo Input 失去输入焦点，不再显示活动输入光标。",
)


def requirement(text):
    return {"text": text, "expectation_basis": {
        "type": "interaction_convention", "reference": "Current control convention"}}


@pytest.mark.parametrize("action,pair", [("type New Todo Input", TYPE_PAIR),
                                         ("blur New Todo Input", BLUR_PAIR)])
def test_observed_paraphrases_merge_without_rewriting_the_requirement(action, pair):
    samples = [[requirement(text)] for text in pair]
    diagnostic = {}
    accepted, unresolved = merge_samples(samples, action_desc=action, diagnostics=diagnostic)
    assert len(accepted) == 1 and not unresolved
    assert accepted[0] in samples[0] + samples[1]
    assert diagnostic["groups"][0]["support_count"] == 2


@pytest.mark.parametrize("action,original,other", [
    ("type New Todo Input", TYPE_PAIR[0], TYPE_PAIR[1].replace("New Todo Input", "Other Input")),
    ("type New Todo Input", TYPE_PAIR[0], TYPE_PAIR[1].replace("应可见地", "不应可见地")),
    ("type New Todo Input", TYPE_PAIR[0], TYPE_PAIR[1].replace("内容。", "内容，并自动保存。")),
    ("type New Todo Input", TYPE_PAIR[0], TYPE_PAIR[1].replace("应可见地", "应在 3 秒内可见地")),
    ("blur New Todo Input", BLUR_PAIR[0], BLUR_PAIR[1].replace("New Todo Input", "Other Input")),
    ("blur New Todo Input", BLUR_PAIR[0], BLUR_PAIR[1].replace("失去输入焦点", "保持输入焦点")),
    ("blur New Todo Input", BLUR_PAIR[0], BLUR_PAIR[1].replace("光标。", "光标，且保存成功。")),
    ("click Save next item", "本次操作后应有可见结果反馈",
     "点击后应出现与保存下一项相符的可见结果，例如保存状态更新或进入下一项。"),
])
def test_new_rules_preserve_objects_negation_limits_and_history_specificity(action, original, other):
    accepted, unresolved = merge_samples([[requirement(original)], [requirement(other)]], action_desc=action)
    assert not accepted and unresolved


def elements(**changes):
    el = {"tag": "input", "input_type": "text", "selector": "#entry", "name": "Entry",
          "value": "A task", "focused": False, "form_key": ""}
    el.update(changes)
    return SimpleNamespace(interactive_elements=lambda: [el])


def test_filled_formless_single_line_input_offers_a_bounded_enter_probe():
    planner = ActionPlanner()
    candidates = planner.extract_candidates(elements())
    action = planner.plan(ExplorerContext(state_id="S-1"), candidates)
    assert action.type == "press" and action.text == "Enter"
    planner.record_result(action, "S-1", True)
    assert planner.plan(ExplorerContext(state_id="S-1"), candidates) is None


@pytest.mark.parametrize("changes", [
    {"tag": "textarea"}, {"contenteditable": True}, {"input_type": "password"},
    {"input_type": "number"}, {"form_key": "#form"}, {"readonly": True}, {"disabled": True},
])
def test_generic_enter_probe_does_not_submit_other_controls(changes):
    assert not any(c.action.type == "press" for c in ActionPlanner().extract_candidates(elements(**changes)))


def test_real_browser_exploration_probes_enter_before_leaving_the_app(http_base_url):
    from alienqa.driver import PlaywrightDriver
    driver = PlaywrightDriver(browser="chromium")
    driver.launch(f"{http_base_url}/demo-app/index.html")
    try:
        driver._page.set_content('''<input id="entry" aria-label="Entry">
            <output id="result"></output><a href="/elsewhere">Project website</a>
            <script>entry.addEventListener('keydown', e => {
              if(e.key==='Enter') {result.textContent=entry.value;entry.value='';}
            });</script>''')
        tracker = explore(driver, StateTracker(), ActionPlanner(), ExploreBudget(max_steps=3))
        assert [a["type"] for a in tracker.action_history()] == ["type", "blur", "press"]
        assert driver.text("#result") == "AlienQA test"
        assert not driver._page.url.endswith("/elsewhere")
    finally:
        driver.close()
