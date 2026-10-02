"""T02 observable mechanics, failure boundaries, and old-package compatibility."""
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from alienqa.driver import Action, PlaywrightDriver, Target
from alienqa.planner import ActionPlanner, ExploreBudget, explore
from alienqa.state import StateTracker
from alienqa.state.signature import signature


@pytest.fixture
def browser(http_base_url):
    d = PlaywrightDriver(browser="chromium")
    d.launch(f"{http_base_url}/demo-app/index.html")
    yield d
    d.close()


def test_target_optional_semantics_roundtrip_and_legacy():
    raw = {"selector": "#save", "role": "button", "name": "Save", "label": "",
           "scope": "#billing", "viewport": {"width": 1280, "height": 800}}
    assert Target.from_dict(raw).name == "Save"
    assert Target.from_dict(asdict(Target.from_dict(raw))).scope == "#billing"
    assert Target.from_dict({"text": "Save"}).scope is None


def test_ambiguous_name_is_not_arbitrarily_clicked(browser):
    browser._page.set_content('<button onclick="this.textContent=\'clicked\'">Save</button><button>Save</button>')
    with pytest.raises(RuntimeError, match="ambiguous_target"):
        browser.execute(Action("click", Target(role="button", name="Save")), timeout=400)
    assert "clicked" not in browser.visible_text()
    assert browser.last_execution["emitted"] is False
    assert browser.last_execution["attempts"][0]["matches"] == 2


def test_scope_separates_identical_save_buttons(browser):
    browser._page.set_content('<form id="billing"><button type="button" onclick="this.textContent=\'Saved\'">Save</button></form><form id="shipping"><button type="button">Save</button></form>')
    browser.execute(Action("click", Target(role="button", name="Save", scope="#billing")))
    assert browser.text("#billing") == "Saved"
    assert browser.text("#shipping") == "Save"


def test_replaced_structural_selector_does_not_click_wrong_sibling(browser):
    browser._page.set_content('<div><button>Save</button></div>')
    el = browser.interactive_elements()[0]
    target = ActionPlanner().extract_candidates(browser)[0].action.target
    browser._page.locator("div").evaluate("el => el.insertAdjacentHTML('afterbegin', '<button>Other</button>')")
    browser._page.get_by_role("button", name="Save").evaluate("el => el.onclick=()=>el.textContent='Saved'")
    browser.execute(Action("click", target))
    assert "Saved" in browser.visible_text()
    assert browser.last_execution["locator"]["strategy"] != "selector"
    assert el["name"] == "Save"


def test_wait_error_does_not_repeat_already_emitted_click(browser, monkeypatch):
    browser._page.set_content('<button id="save" onclick="this.dataset.count=Number(this.dataset.count||0)+1">Save</button>')
    def broken_wait(*args, **kwargs):
        raise RuntimeError("screenshot or wait failed")
    monkeypatch.setattr(browser, "wait_for_settle", broken_wait)
    result = browser.execute(Action("click", Target(selector="#save", text="Save")))
    assert browser._page.locator("#save").get_attribute("data-count") == "1"
    assert result["status"] == "completed" and result["wait"]["status"] == "failed"
    assert len(browser.replay_data()["action_sequence"]) == 1


def test_delayed_feedback_and_infinite_busy_are_different(browser):
    browser._page.set_content('<button id="save" onclick="document.body.setAttribute(\'aria-busy\',\'true\');setTimeout(()=>{document.querySelector(\'output\').textContent=\'Saved\';document.body.removeAttribute(\'aria-busy\')},700)">Save</button><output></output>')
    result = browser.execute(Action("click", Target(selector="#save")))
    assert result["wait"]["status"] == "settled"
    assert "Saved" in browser.visible_text()
    browser._page.set_content('<button onclick="document.body.setAttribute(\'aria-busy\',\'true\')">Save</button>')
    result = browser.execute(Action("click", Target(text="Save")), timeout=700)
    assert result["emitted"] and result["wait"]["status"] == "timeout"
    assert result["wait"]["pending"] is True


def test_controlled_value_reset_is_not_successful_fill(browser):
    browser._page.set_content('<label>Name<input id="name" oninput="setTimeout(()=>this.value=\'\',100)"></label>')
    result = browser.execute(Action("type", Target(selector="#name"), "AlienQA"))
    assert result["value_accepted"] is False
    assert result["status"] == "input_rejected"


def test_explicit_blur_and_visible_validation(browser):
    browser._page.set_content('<label>Email<input id="email" onblur="document.querySelector(\'output\').textContent=\'Email checked\'"></label><output></output>')
    browser.execute(Action("type", Target(selector="#email"), "alienqa@example.com"))
    candidates = ActionPlanner().extract_candidates(browser)
    assert any(c.action.type == "blur" for c in candidates)
    browser.execute(next(c.action for c in candidates if c.action.type == "blur"))
    assert "Email checked" in browser.visible_text()


def test_custom_select_is_expanded_then_option_clicked(browser):
    browser._page.set_content('<div role="combobox" aria-label="Country" aria-expanded="false" onclick="this.setAttribute(\'aria-expanded\',\'true\');document.querySelector(\'[role=listbox]\').hidden=false">Country</div><div role="listbox" hidden><div role="option" aria-selected="false" onclick="this.setAttribute(\'aria-selected\',\'true\');document.querySelector(\'[role=combobox]\').textContent=\'China\'">China</div></div>')
    planner = ActionPlanner()
    first = next(c.action for c in planner.extract_candidates(browser) if c.role == "combobox")
    assert first.type == "click"
    browser.execute(first)
    option = next(c.action for c in planner.extract_candidates(browser) if c.role == "option")
    browser.execute(option)
    assert browser.text("[role=combobox]") == "China"
    assert not any(c.role == "option" for c in planner.extract_candidates(browser))


def test_portal_modal_excludes_background_candidates_and_restores(browser):
    browser._page.set_content('<button id="background">Background</button><div role="dialog" aria-modal="true"><button id="close" onclick="this.parentElement.remove()">Close</button></div>')
    assert [c.text for c in ActionPlanner().extract_candidates(browser)] == ["Close"]
    browser.execute(Action("click", Target(selector="#close")))
    assert [c.text for c in ActionPlanner().extract_candidates(browser)] == ["Background"]


def test_enumeration_limit_frames_and_shadow_report_coverage(browser):
    browser._page.set_content('<iframe src="about:blank"></iframe><div id="host"></div>' + '<button>B</button>' * 205)
    browser._page.locator("#host").evaluate("el=>el.attachShadow({mode:'open'}).innerHTML='<button>Inside</button>'")
    browser.interactive_elements()
    coverage = browser.interaction_coverage()
    assert coverage["truncated"] and coverage["limit"] == 200
    assert coverage["frames"][0]["status"] == "unvisited"
    assert coverage["shadow"]["status"] == "unverified"
    assert coverage["shadow"]["open_roots"] == 1


def test_visible_control_state_changes_and_reorder_does_not(browser):
    browser._page.set_content('<label>Email<input></label><label>Name<input></label><button aria-expanded="false">Menu</button>')
    before = browser.form_state()
    browser._page.locator("body").evaluate("el=>el.insertBefore(el.children[1],el.children[0])")
    assert signature("/", "Form", before) == signature("/", "Form", browser.form_state())
    browser._page.get_by_role("button").evaluate("el=>el.setAttribute('aria-expanded','true')")
    assert signature("/", "Form", before) != signature("/", "Form", browser.form_state())


def test_failure_attempt_is_saved_without_success_edge(tmp_path):
    driver = SimpleNamespace(url=lambda: "/", visible_text=lambda: "Home",
                             execute=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("blocked")))
    tracker = StateTracker()
    state = tracker.capture(driver)
    with pytest.raises(RuntimeError):
        tracker.capture(driver, Action("click", Target(text="Save")), step_id="ST-00001")
    assert tracker.attempts()[0]["step_id"] == "ST-00001"
    assert tracker.attempts()[0]["from"] == state.id
    assert tracker.attempts()[0]["status"] == "failed"
    assert tracker.graph().edges == [] and tracker.action_history() == []
    tracker.save(tmp_path / "states.json")
    assert StateTracker.load(tmp_path / "states.json").attempts() == tracker.attempts()


def test_sample_values_respect_numeric_max_and_email_length():
    from alienqa.planner.planner import _sample_value
    assert float(_sample_value({"input_type": "number", "min": "-8", "max": "-2"})) <= -2
    assert _sample_value({"input_type": "email", "maxlength": 8}) == "a@b.co"
    assert _sample_value({"input_type": "email", "maxlength": 3}) is None


def test_exhausted_deadline_emits_no_action(browser):
    import time
    browser.set_deadline(time.monotonic() - 1)
    with pytest.raises(RuntimeError, match="budget"):
        browser.execute(Action("click", Target(selector="#greet")))
    assert browser.replay_data()["action_sequence"] == []


def test_coordinate_replay_refuses_changed_viewport(browser):
    target = Target(x=20, y=20, viewport={"width": 800, "height": 600})
    with pytest.raises(RuntimeError, match="viewport"):
        browser.execute(Action("click", target))
    assert browser.last_execution["emitted"] is False


def test_old_action_sequence_reads_without_step_id(browser):
    browser.execute(Action.from_dict({"type": "click", "target": {"selector": "#greet"}}))
    assert browser.text("#status") == "greeted"
    assert browser.replay_data()["attempts"][0]["status"] == "completed"


def test_hash_and_history_routes_are_observed(browser):
    browser._page.set_content('<button onclick="history.pushState({},\'\',\'?tab=2#details\')">Details</button>')
    browser.set_runtime_context("run", "ST-00001", "A-00001", "action")
    browser.execute(Action("click", Target(text="Details")))
    data = browser.replay_data()
    assert data["final_url"].endswith("?tab=2#details")
    assert data["action_sequence"][0]["step_id"] == "ST-00001"
    assert data["attempts"][0]["url_after"].endswith("?tab=2#details")


def test_storage_state_and_expired_cookie_access_result(tmp_path):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            if self.path == '/protected' and 'session=t02-private-cookie' not in self.headers.get('Cookie', ''):
                self.send_response(302)
                self.send_header('Location', '/login')
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'<button>Save</button><output id="stored"></output><script>document.querySelector("output").textContent=localStorage.getItem("seed")||"Login required"</script>')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    origin=f'http://127.0.0.1:{server.server_address[1]}'
    storage={'cookies':[{'name':'session','value':'t02-private-cookie','domain':'127.0.0.1','path':'/','expires':-1,'httpOnly':True,'secure':False,'sameSite':'Lax'}],
             'origins':[{'origin':origin,'localStorage':[{'name':'seed','value':'restored'}]}]}
    first=PlaywrightDriver(browser='chromium')
    second=PlaywrightDriver(browser='chromium')
    expired=PlaywrightDriver(browser='chromium')
    try:
        first.launch(origin+'/protected',storage_state=storage)
        assert first.url().endswith('/protected') and first.text('#stored')=='restored'
        package=first.replay_data()
        first.close()
        second.launch(package['url'],storage_state=package['storage_state'])
        assert second.url().endswith('/protected') and second.text('#stored')=='restored'
        second.close()
        storage['cookies'][0]['expires']=1
        expired.launch(origin+'/protected',storage_state=storage)
        assert expired.url().endswith('/login')
        assert expired.access_result['redirected'] is True
        assert expired.replay_data()['url']==origin+'/protected'
        assert expired.replay_data()['limitations']['session_storage']=='not_restored'
    finally:
        first.close(); second.close(); expired.close()
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_legacy_digest_does_not_prove_new_state_coverage(tmp_path):
    import json
    tracker=StateTracker()
    old=tracker.observe('/', 'Home')
    data=tracker.graph().to_dict()
    path=tmp_path/'legacy.json'
    path.write_text(json.dumps(data))
    loaded=StateTracker.load(path)
    assert loaded.is_new('/', 'Home')
    assert loaded.observe('/', 'Home').id != old.id


def test_replay_interruption_reports_original_step_id(tmp_path):
    import json
    from alienqa.replay import ReplayEngine
    driver=SimpleNamespace(launch=lambda *a,**k:None,close=lambda:None,collect_runtime=lambda:SimpleNamespace(),
                           execute=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('blocked')))
    pkg={'replay':{'url':'https://app.test/', 'action_sequence':[{'type':'click','target':{'text':'Save'},'step_id':'ST-00007'}]}}
    (tmp_path/'F-001.json').write_text(json.dumps(pkg))
    result=ReplayEngine(tmp_path,driver_factory=lambda:driver).replay('F-001')
    assert result.status=='failed' and result.interrupted_step_id=='ST-00007'
    assert 'ST-00007' in result.note


def test_perform_error_with_unknown_emission_does_not_try_other_locator(browser, monkeypatch):
    calls=[]
    def uncertain(*args,**kwargs):
        calls.append('dispatch')
        raise RuntimeError('page closed during click; emission unknown')
    monkeypatch.setattr(browser,'_perform',uncertain)
    with pytest.raises(RuntimeError):
        browser.execute(Action('click',Target(selector='#greet',text='Greet')))
    assert calls==['dispatch']
    assert browser.last_execution['emitted'] is None
    assert browser.replay_data()['prefix_complete'] is False


def test_uncertain_action_is_not_retried_as_a_confirmed_failure():
    planner=ActionPlanner()
    action=Action('click',Target(text='Save'))
    planner.record_result(action,'S-1',False)
    planner.record_uncertain(action,'S-1')
    assert not planner._available(action,'S-1')


def test_meaningful_time_feedback_is_not_clock_noise():
    assert signature('/', 'Saved at 2026-10-02 12:00:00') != signature('/', 'Saved at 2026-10-02 12:00:01')
    assert signature('/', 'Appointment 12:00:00') != signature('/', 'Appointment 13:00:00')
    assert signature('/', 'Home\n2026-10-02 12:00:00') == signature('/', 'Home\n2026-10-02 12:00:01')


def test_evidence_retains_new_target_semantics():
    from alienqa.evidence.engine import _serialize_target
    target=Target(role='button',name='Save',scope='#profile',viewport={'width':1280,'height':800})
    result=_serialize_target(target)
    assert result['name']=='Save' and result['scope']=='#profile'
    assert result['viewport']==target.viewport
