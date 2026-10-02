"""Opt-in locked real-framework tests. Run scripts/prepare_t02_frameworks.py first."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import urlopen

import pytest

from alienqa.driver import Action, PlaywrightDriver, Target
from alienqa.planner import ActionPlanner, ExploreBudget, explore
from alienqa.replay import ReplayEngine
from alienqa.state import StateTracker

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / 'examples/open-source/t02-frameworks'


@pytest.fixture(scope='module')
def framework_urls():
    urls, processes, logs = {}, [], []
    directory = ROOT / 'artifacts/evaluation/t02-frameworks'
    directory.mkdir(parents=True, exist_ok=True)
    try:
        for family in ('vite', 'next'):
            dest = WORKSPACE / family
            assert (dest / 'node_modules').is_dir(), 'Explicitly prepare framework workspace first'
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            log = (directory / f'{family}-server.log').open('w')
            logs.append(log)
            process = subprocess.Popen(['npm', 'run', 'start', '--', '--port', str(port)], cwd=dest,
                                       env={**os.environ, 'NEXT_TELEMETRY_DISABLED': '1',
                                            'npm_config_cache': str(WORKSPACE / '.npm-cache')},
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(process)
            url = f'http://127.0.0.1:{port}'
            for attempt in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f'{family} server failed; inspect {directory}')
                try:
                    with urlopen(url + ('/react.html' if family == 'vite' else '/'), timeout=1):
                        break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError(f'{family} server did not become ready')
            urls[family] = url
        yield urls
    finally:
        import signal
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        for log in logs:
            log.close()


CASES = [('vite','/react.html'), ('vite','/vue.html'), ('next','/'), ('next','/legacy')]


@pytest.mark.parametrize('family,path', CASES)
def test_t05_framework_form_navigation_fault_independent_replay(framework_urls, family, path):
    from copy import deepcopy
    import tempfile
    from alienqa.evidence import EvidenceEngine
    from alienqa.observation.runtime_observer import RuntimeObserver
    directory = ROOT / 'artifacts/evaluation/t05-frameworks'
    directory.mkdir(parents=True, exist_ok=True)
    case = Path(tempfile.mkdtemp(prefix=family+'-', dir=directory))
    driver = PlaywrightDriver(browser='chromium', viewport={'width': 1024, 'height': 768})
    try:
        driver.launch(framework_urls[family] + path)
        for index, action in enumerate([Action('type', Target(label='Email'), 'alienqa@example.com'),
                                        Action('click', Target(role='button', name='Save')),
                                        Action('click', Target(text='Details'))], 1):
            driver.set_runtime_context('t05', f'ST-{index}', f'A-{index}', 'action')
            executed = driver.execute(action)
            assert executed['status'] == 'completed' and executed['wait']['status'] == 'settled'
        before = deepcopy(driver.collect_runtime())
        target = Action('click', Target(role='button', name='Trigger fault'))
        driver.set_runtime_context('t05', 'ST-4', 'A-4', 'action')
        driver.execute(target)
        runtime = RuntimeObserver().observe(driver, before)
        evs = EvidenceEngine(case / 'artifacts').build_technical(runtime, target, driver=driver, step_id='ST-4', action_id='A-4')
        assert len(evs) == 1
        evidence = evs[0]
    finally:
        driver.close()
    engine = ReplayEngine(case / 'replay')
    engine.save(evidence)
    result = engine.replay(evidence.id)
    (case / 'result.json').write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    assert result.status == 'reproduced', result.note
    assert len(result.executed_steps) == 4
    assert result.executed_steps[-1]['step_id'] == 'ST-4'
    assert result.matched_basis[0]['kind'] == 'page_error'


@pytest.mark.parametrize('family,path', CASES)
def test_real_controlled_form_feedback_and_independent_replay(framework_urls, family, path):
    driver = PlaywrightDriver(browser='chromium')
    driver.launch(framework_urls[family] + path)
    try:
        planner = ActionPlanner()
        actions = []
        for kind in ('type','blur','click'):
            candidates = planner.extract_candidates(driver)
            action = next(c.action for c in candidates if c.action.type == kind and
                          (kind != 'click' or c.text == 'Save'))
            driver.set_runtime_context('t02', f'ST-{len(actions)+1:05d}', f'A-{len(actions)+1:05d}', 'action')
            result = driver.execute(action)
            assert result['status'] == 'completed' and result['wait']['status'] == 'settled'
            actions.append(action)
        assert 'Saved alienqa@example.com' in driver.visible_text()
        driver.set_runtime_context('t02','ST-00004','A-00004','action')
        details = next(c.action for c in planner.extract_candidates(driver) if c.text == 'Details')
        driver.execute(details)
        assert '#details' in driver.url() or '/details?tab=2#summary' in driver.url()
        case_dir = ROOT / 'artifacts/evaluation/t02-frameworks/cases' / (family+'-'+(path.strip('/').replace('.','-') or 'app'))
        case_dir.mkdir(parents=True, exist_ok=True)
        after = case_dir / 'after.png'
        after.write_bytes(driver.screenshot())
        replay = driver.replay_data()
        driver.close()
        package = {'id':'F-001', 'replay':replay, 'artifacts':{'after':str(after)}}
        engine = ReplayEngine(case_dir / 'replay', driver_factory=lambda:PlaywrightDriver(browser='chromium'))
        engine.replay_dir.mkdir(exist_ok=True)
        (engine.replay_dir / 'F-001.json').write_text(json.dumps(package))
        replayed = engine.replay('F-001')
        assert replayed.status == 'reproduced', replayed.note
        assert [s['step_id'] for s in replayed.executed_steps] == [f'ST-{i:05d}' for i in range(1,5)]
        (case_dir / 'result.json').write_text(json.dumps(replayed.to_dict(), ensure_ascii=False, indent=2))
    finally:
        driver.close()


def test_react_portal_and_reset_pair(framework_urls):
    driver = PlaywrightDriver(browser='chromium')
    driver.launch(framework_urls['vite']+'/react.html')
    try:
        driver.execute(Action('click',Target(role='button',name='Open dialog')))
        assert [c.text for c in ActionPlanner().extract_candidates(driver)] == ['Close']
        driver.execute(next(c.action for c in ActionPlanner().extract_candidates(driver)))
        assert any(c.text=='Save' for c in ActionPlanner().extract_candidates(driver))
        driver.navigate(framework_urls['vite']+'/react.html?mode=reset')
        result=driver.execute(Action('type',Target(label='Email'),'alienqa@example.com'))
        assert result['status']=='input_rejected' and result['value_accepted'] is False
    finally:
        driver.close()


@pytest.mark.parametrize('mode,expected',[('', 'China'), ('?mode=option-fails','Country')])
def test_vue_custom_select_normal_and_nonchanging_pair(framework_urls,mode,expected):
    driver=PlaywrightDriver(browser='chromium')
    driver.launch(framework_urls['vite']+'/vue.html'+mode)
    try:
        planner=ActionPlanner()
        driver.execute(next(c.action for c in planner.extract_candidates(driver) if c.role=='combobox'))
        driver.execute(next(c.action for c in planner.extract_candidates(driver) if c.role=='option'))
        assert driver.text('[role=combobox]')==expected
        assert not any(c.role=='option' for c in planner.extract_candidates(driver))
    finally:
        driver.close()


@pytest.mark.parametrize('family,path',[('vite','/react.html?mode=missing'),('vite','/vue.html?mode=missing'),('next','/?missing=1')])
def test_missing_feedback_pair_does_not_fabricate_success(framework_urls,family,path):
    driver=PlaywrightDriver(browser='chromium')
    driver.launch(framework_urls[family]+path)
    try:
        driver.execute(Action('type',Target(label='Email'),'alienqa@example.com'))
        driver.execute(Action('click',Target(role='button',name='Save')))
        assert 'Saved ' not in driver.visible_text()
        # Driver reports execution facts; this test does not invent a model judgment.
        assert driver.last_execution['wait']['status']=='settled'
    finally:
        driver.close()


def test_finite_planner_reaches_react_submission(framework_urls):
    driver=PlaywrightDriver(browser='chromium')
    driver.launch(framework_urls['vite']+'/react.html')
    try:
        tracker=explore(driver,StateTracker(),ActionPlanner(ExploreBudget(max_steps=4)))
        assert 'Saved alienqa@example.com' in driver.visible_text()
        assert len(tracker.attempts())==4
        assert tracker.attempts()[2]['execution']['wait']['status']=='settled'
    finally:
        driver.close()


@pytest.mark.parametrize('family,path,missing', [('vite','/react.html',False),('vite','/vue.html',False),
                                               ('next','/',False),('next','/legacy',False),
                                               ('vite','/react.html?mode=missing',True)])
def test_production_pipeline_commits_framework_facts_and_evidence(framework_urls,family,path,missing,monkeypatch):
    """Stub inference verifies wiring only, never real-model accuracy."""
    from types import SimpleNamespace
    import tempfile
    from alienqa.llm import LLMConfig,Role,RoleConfig
    from alienqa.loader import ProjectLoader
    from alienqa.mapper import ProductMap
    from alienqa.pipeline import AlienQAPipeline
    from alienqa.run_writer import load_snapshot
    from alienqa.review import ReportBuilder,ReviewState
    directory=Path(tempfile.mkdtemp(prefix='pipeline-'+family+'-',dir=ROOT/'artifacts/evaluation/t02-frameworks'))
    def completion(**kwargs):
        role=kwargs['model'].split('/')[-1]
        if role=='gist':
            text='A visible profile form.'
        elif role=='expectation':
            text=json.dumps({'expectations':[{'text':'本次操作后应有可见结果反馈','expectation_basis':{'type':'interaction_convention','reference':'交互操作应说明结果'}}]})
        elif role=='visual':
            text=json.dumps({'changes':['other'],'summary':'查看已保存的前后截图'})
        elif role=='judge':
            step=load_snapshot(directory)['steps'][-1]
            assert step['execution']['wait']['status']=='settled'
            assert (directory/'steps'/step['step_id']/'after.png').is_file()
            target=step['action']['target']
            mismatch=step['action']['type']=='click' and target.get('text')=='Save' and 'Saved ' not in step['visible_result']
            payload={'status':'mismatch' if mismatch else 'passed','mismatches':[]}
            if mismatch:
                expected=step['expectations'][0]
                payload['mismatches']=[{'expectation_id':expected['id'],'expectation':expected['text'],
                                      'observation':'No visible save result','level':'medium','reasoning':'用户需要获知操作结果'}]
            text=json.dumps(payload)
        elif role=='reporter':
            text=''
        else:
            text=json.dumps({'root_cause_hypothesis':'待复核','reproduction_steps':[],'technical_evidence':{},'affected_components':[]})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))],usage=None)
    monkeypatch.setattr('alienqa.llm.client._litellm',lambda:SimpleNamespace(completion=completion))
    monkeypatch.setattr('alienqa.pipeline.ProductMapper.map_from_browser',lambda *args:ProductMap())
    config=LLMConfig(roles={r.value:RoleConfig(model='test/'+r.value) for r in Role})
    pipeline=AlienQAPipeline(config,samples=1,max_actions=3,browser='chromium',run_dir=directory,
                             artifacts_dir=directory/'artifacts',verbose=False)
    result=pipeline.collect(ProjectLoader().load_browser(framework_urls[family]+path))
    saved=load_snapshot(directory)
    assert all(s['status'] in {'passed','mismatch'} for s in result.steps), result.steps
    # A framework may add shadow regions beyond the verified main-page path.
    # Coverage warnings must remain visible even when the tested path succeeds.
    assert all(d['stage']=='interaction_coverage' for d in result.diagnostics), result.diagnostics
    assert [s['action']['type'] for s in saved['steps']]==['type','blur','click']
    assert all(s['execution']['step_id']==s['step_id']==s['trajectory']['step_id'] for s in saved['steps'])
    assert saved['steps'][-1]['status']==('mismatch' if missing else 'passed')
    if missing:
        evidence=result.evidences[0]
        assert evidence.expectation_id==saved['steps'][-1]['expectations'][0]['id']
        assert evidence.action['target']['name']=='Save' and evidence.action['target']['scope']=='#profile'
        replayed=ReplayEngine(directory/'artifacts/replay').replay(evidence.id)
        assert replayed.status=='reproduced',replayed.note
        assert len(replayed.executed_steps)==3
    report=ReportBuilder(pipeline.client).build(result.evidences,ReviewState(),mode='analysis',diagnostics=result.review_diagnostics,
                                               scan_context={**saved,'run_dir':str(directory)})
    assert 'execution' in report.html and 'settled' in report.html
    (directory/'analysis.html').write_text(report.html)
