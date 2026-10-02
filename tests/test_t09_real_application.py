"""Opt-in pinned upstream TodoMVC browser baseline. No model/effect claims."""
import json
from pathlib import Path
import subprocess
import uuid

from playwright.sync_api import expect

from alienqa.driver import Action, PlaywrightDriver, Target
from alienqa.evidence import Evidence
from alienqa.loader import Project
from alienqa.local_run import serve_project
from alienqa.planner import ActionPlanner, ExploreBudget, explore
from alienqa.replay import ReplayEngine
from alienqa.state import StateTracker
from scripts.prepare_t09_todomvc import COMMIT, WORKSPACE, prepare

ROOT=Path(__file__).resolve().parents[1]


def test_upstream_todomvc_autonomous_planner_creates_todo_in_three_actions():
    app = prepare()
    project = Project(root=str(app), framework="React", app_dir=str(app))
    server, _ = serve_project(project)
    driver = PlaywrightDriver(browser="chromium")
    try:
        driver.launch(project.base_url)
        tracker = explore(driver, StateTracker(), ActionPlanner(), ExploreBudget(max_steps=3))
        assert [a["type"] for a in tracker.action_history()] == ["type", "blur", "press"]
        expect(driver._page.locator(".todo-list li")).to_have_count(1)
        expect(driver._page.locator(".todo-list li label")).to_have_text("AlienQA test")
    finally:
        driver.close()
        server.shutdown()
        server.server_close()


def test_upstream_todomvc_add_toggle_filter_and_independent_replay():
    app=prepare()
    project=Project(root=str(app),framework='React',app_dir=str(app))
    server,_=serve_project(project)
    output=ROOT/'artifacts/evaluation/t09-todomvc'/uuid.uuid4().hex
    output.mkdir(parents=True)
    driver=PlaywrightDriver(browser='chromium')
    try:
        driver.launch(project.base_url)
        for action in [Action('type',Target(selector='.new-todo'),'Read analysis'),
                       Action('press',Target(selector='.new-todo'),'Enter'),
                       Action('click',Target(selector='.todo-list .toggle')),
                       Action('click',Target(role='link',name='Active'))]:
            assert driver.execute(action)['status']=='completed'
        expect(driver._page.locator('.todo-list li')).to_have_count(0)
        assert driver._page.url.endswith('#/active')
        replay=driver.replay_data()
        replay['static_server']=project.artifacts['static_server']
        image=output/'after.png';image.write_bytes(driver.screenshot())
    finally:
        driver.close();server.shutdown();server.server_close()
    engine=ReplayEngine(output/'replay')
    engine.save(Evidence(id='EV-todomvc',replay=replay,artifacts={'after':str(image)}))
    result=engine.replay('EV-todomvc')
    assert result.status=='reproduced',result.note
    (output/'summary.json').write_text(json.dumps({'upstream':'https://github.com/tastejs/todomvc',
        'commit':COMMIT,'package':json.loads((app/'package.json').read_text()),'browser':replay.get('browser'),
        'add_toggle_filter':'passed','independent_replay':result.status,'real_model_calls':0,
        'limits':'Small framework showcase; browser mechanics, not human usefulness/model quality'},indent=2))
