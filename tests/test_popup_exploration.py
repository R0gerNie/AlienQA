"""Visible portal ownership, input branches and focus facts (no semantic approval)."""
from dataclasses import asdict
import json
from types import SimpleNamespace

import pytest

from alienqa.context import ExplorerContext
from alienqa.driver import Action, Target
from alienqa.driver.action import describe_visible_action
from alienqa.expectation import ExpectationEngine, PageInfo
from alienqa.loader import UnitScope
from alienqa.planner import ActionPlanner
from test_t02_interactions import browser
from test_t03_cognition import Client, context

PORTAL = '''<section id="editor"><button id="tools" aria-controls="menu" aria-haspopup="menu" aria-expanded="false"
 onclick="this.setAttribute('aria-expanded','true');document.querySelector('#menu').hidden=false;document.body.style.pointerEvents='none'">Tools</button>
 <button id="save">Save</button></section><button id="outside">Outside</button>
 <div id="menu" role="menu" hidden style="pointer-events:auto" onkeydown="if(event.key==='Escape'){this.hidden=true;document.body.style.pointerEvents='auto';document.querySelector('#tools').setAttribute('aria-expanded','false')}">
 <button role="menuitem" id="item" onclick="this.textContent='Selected'">Choose</button></div>'''


def test_owned_portal_menu_excludes_blocked_background_and_can_return(browser):
    browser._page.set_content(PORTAL)
    scope = UnitScope(selectors=['#tools', '#save'])
    browser.execute(Action('click', Target(selector='#tools')))
    planner = ActionPlanner()
    candidates = planner.extract_candidates(browser)
    assert any(c.selector == '#item' and scope.matches(c) for c in candidates)
    assert not any(c.selector in {'#tools', '#outside', '#save'} for c in candidates)
    chosen = planner.plan(ExplorerContext(state_id='menu'), candidates)
    browser.execute(chosen)
    planner.record_result(chosen, 'menu', True)
    candidates = planner.extract_candidates(browser)
    escape = next(c.action for c in candidates if c.action.type == 'press' and c.action.text == 'Escape')
    assert scope.matches(next(c for c in candidates if c.action is escape))
    browser.execute(escape)
    assert any(c.selector == '#save' for c in planner.extract_candidates(browser))
    assert not scope.matches(next(c for c in planner.extract_candidates(browser) if c.selector == '#outside'))


def test_return_from_menu_prefers_remaining_unit_work_to_reopening(browser):
    browser._page.set_content(PORTAL)
    planner = ActionPlanner()
    trigger = next(c.action for c in planner.extract_candidates(browser) if c.selector == '#tools')
    browser.execute(trigger)
    planner.record_result(trigger, 'before', True)
    browser.execute(next(c.action for c in planner.extract_candidates(browser) if c.action.text == 'Escape'))
    scoped = [c for c in planner.extract_candidates(browser) if UnitScope(selectors=['#tools','#save']).matches(c)]
    assert planner.plan(ExplorerContext(state_id='changed-by-menu'), scoped).target.selector == '#save'


def test_unrelated_portal_does_not_expand_unit(browser):
    browser._page.set_content(PORTAL.replace('hidden style=', 'style=').replace('aria-expanded="false"', 'aria-expanded="true"'))
    scope = UnitScope(selectors=['#save'])
    assert not any(scope.matches(c) for c in ActionPlanner().extract_candidates(browser))


def test_nested_menu_inherits_original_unit_owner(browser):
    browser._page.set_content('''<button id="tools" aria-controls="menu" aria-expanded="true">Tools</button>
    <div id="menu" role="menu"><button id="more" role="menuitem" aria-controls="sub" aria-expanded="true">More</button></div>
    <div id="sub" role="menu"><button id="child" role="menuitem">Child</button></div>''')
    candidates = ActionPlanner().extract_candidates(browser)
    assert any(c.selector == '#child' and UnitScope(selectors=['#tools']).matches(c) for c in candidates)
    assert not any(c.selector == '#more' for c in candidates)


def test_popup_without_aria_connection_uses_observed_scoped_trigger(browser):
    browser._page.set_content('''<button id="tools" onclick="document.querySelector('#menu').hidden=false">Tools</button>
    <div id="menu" role="menu" hidden><button role="menuitem" id="item">Choose</button></div>''')
    browser.execute(Action('click', Target(selector='#tools', text='Tools')))
    assert any(c.selector == '#item' and UnitScope(selectors=['#tools']).matches(c)
               for c in ActionPlanner().extract_candidates(browser))


def test_multiple_unrelated_modals_remain_ambiguous(browser):
    browser._page.set_content('<div role="dialog" aria-modal="true"><button>A</button></div><div role="dialog" aria-modal="true"><button>B</button></div>')
    assert browser.interactive_elements() == []
    assert browser.interaction_coverage()['ambiguous_modal']


def test_icon_action_has_visible_identity_without_locator_or_secret(browser):
    browser._page.set_content('<button id="PRIVATE_SELECTOR" aria-haspopup="menu" aria-expanded="false"><svg><path d="M0 0"></path></svg></button>')
    action = ActionPlanner().extract_candidates(browser)[0].action
    engine = ExpectationEngine(Client(['{"expectations":[]}']), samples=1)
    engine.expect(context(), PageInfo(), action)
    target = engine.last_input['action_target']
    assert target['role'] == 'button' and target['popup'] == 'menu'
    assert target['position']['width'] > 0
    assert '当前控件' not in engine.last_input['action']
    assert 'PRIVATE_SELECTOR' not in engine.client.prompts[0]
    restored = Action.from_dict(asdict(action))
    assert restored.target.visible == action.target.visible


def test_action_target_allowlist_keeps_sensitive_values_out():
    engine = ExpectationEngine(Client(['{"expectations":[]}']), samples=1)
    action = Action('type', Target(text='Password', visible={'value':'PASSWORD_SECRET', 'selector':'PRIVATE',
        'role':'textbox', 'value_state':'nonempty', 'focused':True}), 'PASSWORD_SECRET')
    engine.expect(context(), PageInfo(), action)
    assert engine.last_input['action_target']['value_state'] == 'nonempty'
    assert 'PASSWORD_SECRET' not in engine.client.prompts[0] and 'PRIVATE' not in engine.client.prompts[0]
    assert describe_visible_action(Action('click', Target(name='Visible name'))) == 'click Visible name'


def test_json_branches_progress_without_repeating_valid_input(browser):
    browser._page.set_content('<label>Your JSON<textarea id="json" placeholder="Paste your JSON here..."></textarea></label>')
    planner = ActionPlanner()
    seen=[]
    for index in range(7):
        candidates=planner.extract_candidates(browser)
        action=planner.plan(ExplorerContext(state_id=f'S-{index}'), candidates)
        if action is None:break
        browser.execute(action)
        planner.record_result(action, f'S-{index}', True)
        if action.type=='type':seen.append((action.input_branch, action.text))
    assert [branch for branch,value in seen] == ['valid','invalid','empty']
    assert json.loads(seen[0][1]) == {'name':'AlienQA','count':2}
    with pytest.raises(json.JSONDecodeError):json.loads(seen[1][1])
    assert seen[2][1] == ''


def test_json_branch_does_not_bypass_explicit_pattern_constraints():
    from alienqa.planner.planner import _sample_value
    assert _sample_value({'name':'JSON','pattern':'[a-z]+'}) is None


def test_blur_execution_records_before_after_focus_without_values(browser):
    browser._page.set_content('<label>Password<input id="secret" type="password"></label>')
    browser.execute(Action('type', Target(selector='#secret'), 'PASSWORD_SECRET'))
    browser.set_runtime_context('run', 'ST-00002', 'A-00002', 'action')
    result=browser.execute(Action('blur', Target(selector='#secret')))
    focus=result['focus_observation']
    assert focus['before']['target_focused'] is True and focus['after']['target_focused'] is False
    assert focus['observation_ref']=='scan.json#steps/ST-00002/execution/focus_observation'
    assert 'PASSWORD_SECRET' not in json.dumps(focus)


def test_judge_receives_focus_facts_with_the_frozen_step_identity():
    from alienqa.observation import Observation
    from test_t03_cognition import payload
    client=Client([payload(), '{"status":"passed","mismatches":[]}'])
    engine=ExpectationEngine(client, samples=1)
    expectations=engine.expect(context(), PageInfo(), Action('blur', Target(text='Input')))
    obs=Observation(before_image=b'a',after_image=b'b',run_id='run',step_id='ST-00002',action_id='A-00002')
    # Identity is whatever the test context freezes, never a future step.
    for key in ('run_id','step_id','action_id'):setattr(obs,key,getattr(expectations[0],key))
    obs.action_desc=expectations[0].action_desc
    obs.control_state={'before':{'target_focused':True},'after':{'target_focused':False},
                       'observation_ref':'scan.json#steps/ST-00002/execution/focus_observation'}
    engine.evaluate(expectations, obs)
    assert 'target_focused' in client.prompts[-1]
    assert 'focus_observation' in client.prompts[-1]


def test_pipeline_explores_owned_menu_returns_and_saves_with_focus_lineage(monkeypatch, http_base_url, tmp_path):
    from alienqa.llm import LLMConfig, Role, RoleConfig
    from alienqa.loader import ProjectLoader
    from alienqa.mapper import ProductMap
    from alienqa.pipeline import AlienQAPipeline
    from alienqa.run_writer import load_snapshot
    from test_t03_cognition import payload
    judge_packets=[]
    def completion(**kwargs):
        role=kwargs['model'].split('/')[-1]
        if role=='expectation':data=json.loads(payload('一般交互惯例','interaction_convention','操作后应能看到结果'))
        elif role=='judge':
            saved=load_snapshot(tmp_path);step=saved['steps'][-1]
            assert step['execution_status']=='completed'
            judge_packets.append(str(kwargs['messages']))
            data={'status':'passed','mismatches':[]}
        elif role=='visual':data={'changes':['other'],'summary':'Observed local controls'}
        else:data={}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data)))], usage=None)
    monkeypatch.setattr('alienqa.llm.client._litellm', lambda:SimpleNamespace(completion=completion))
    monkeypatch.setattr('alienqa.pipeline.ProductMapper.map_from_browser', lambda *args:ProductMap())
    monkeypatch.setattr('alienqa.pipeline.UnitLocator.locate', lambda *args:UnitScope(selectors=['#memo','#tools','#save']))
    config=LLMConfig(roles={role.value:RoleConfig(model=f'test/{role.value}') for role in Role})
    result=AlienQAPipeline(config,samples=2,max_actions=7,browser='chromium',run_dir=tmp_path,artifacts_dir=tmp_path,
                          unit='Memo editor',verbose=False).collect(ProjectLoader().load_browser(http_base_url+'/popup-app/index.html'))
    assert any(s['action']['target']['selector']=='#item' for s in result.steps)
    assert any(s['action']['target']['selector']=='#save' and s['execution_status']=='completed' for s in result.steps)
    assert not any(s['action']['target']['selector']=='#outside' for s in result.steps)
    blur=next(s for s in result.steps if s['action']['type']=='blur')
    assert blur['execution']['focus_observation']['after']['target_focused'] is False
    assert any('focus_observation' in packet for packet in judge_packets)
    assert all(s['execution_status']=='completed' for s in result.steps)
    assert result.scope.selectors==['#memo','#tools','#save']


def test_json_form_submits_valid_branch_before_testing_invalid_variants(browser):
    browser._page.set_content('''<form onsubmit="event.preventDefault();document.querySelector('output').textContent=JSON.parse(document.querySelector('textarea').value).name">
    <label>JSON<textarea required></textarea></label><button type="submit">Save</button></form><output></output>''')
    planner=ActionPlanner()
    for index in range(3):
        action=planner.plan(ExplorerContext(state_id=f'S-{index}'),planner.extract_candidates(browser))
        assert action is not None
        browser.execute(action)
        planner.record_result(action, f'S-{index}',True)
    assert browser.text('output')=='AlienQA'


def test_static_navigation_menus_do_not_block_main_page_exploration(browser):
    browser._page.set_content('''<aside><div role="menu"><a href="#one">One</a></div><div role="menu"><a href="#two">Two</a></div></aside>
    <label>Your JSON<textarea placeholder="Paste your JSON here..."></textarea></label>''')
    candidates=ActionPlanner().extract_candidates(browser)
    assert any(c.action.input_branch=='valid' for c in candidates)
    assert not browser.interaction_coverage().get('ambiguous_modal')
