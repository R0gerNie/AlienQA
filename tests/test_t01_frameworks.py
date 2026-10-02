"""Opt-in actual Next src/group/dynamic acceptance on locked T02 dependencies."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
from urllib.request import urlopen

import pytest

from alienqa.driver import Action, PlaywrightDriver, Target
from alienqa.evidence import EvidenceEngine
from alienqa.loader import ProjectLoader
from alienqa.local_run import select_project
from alienqa.observation.runtime_observer import RuntimeObserver
from alienqa.replay import ReplayEngine

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / 'examples/open-source/t01-frameworks'
OUTPUT = ROOT / 'artifacts/evaluation/t01-frameworks'


@pytest.fixture(scope='module')
def next_url():
    dest = WORKSPACE / 'apps/web'
    assert (dest / '.next/BUILD_ID').is_file(), 'Run scripts/prepare_t01_frameworks.py first'
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    with (OUTPUT / 'next-server.log').open('w') as log:
        process = subprocess.Popen(['npm', 'run', 'start', '--', '--port', str(port)], cwd=dest,
            env={**os.environ, 'NEXT_TELEMETRY_DISABLED': '1', 'npm_config_cache': str(WORKSPACE / '.npm-cache')},
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        url = f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Next failed; inspect next-server.log')
                try:
                    with urlopen(url + '/settings', timeout=1):
                        break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Next readiness timeout')
            yield url
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)


@pytest.mark.parametrize('link,template,heading', [
    ('User seven', '/users/[id]', 'User 7'), ('Record seven', '/records/[id]', 'Record 7')])
def test_src_group_ssr_hydration_real_dynamic_link_and_replay(next_url, link, template, heading):
    from copy import deepcopy
    project = select_project(ProjectLoader(), str(WORKSPACE), 'apps/web')
    assert project.app_dir == str(WORKSPACE / 'apps/web')
    assert '/settings' in project.routes and template in project.routes
    assert next(h for h in project.route_hints if h['path'] == template)['template'] is True
    assert all(p.startswith('apps/web/src/') for p in project.entry_points)
    with urlopen(next_url + '/settings') as response:
        assert b'Grouped settings' in response.read()  # actual SSR before hydration
    driver = PlaywrightDriver(browser='chromium')
    try:
        driver.launch(next_url + '/settings')
        driver.execute(Action('type', Target(label='Email'), 'alienqa@example.com'))
        driver.execute(Action('click', Target(role='button', name='Save')))
        assert driver._page.get_by_role('status').inner_text() == 'Saved alienqa@example.com'
        driver.execute(Action('click', Target(role='link', name=link)))
        assert driver._page.get_by_role('heading', name=heading, exact=True).count() == 1
        assert driver._page.url.endswith('/7?tab=2#profile')
        driver._page.reload()
        assert driver._page.get_by_role('heading', name=heading, exact=True).count() == 1
        before = deepcopy(driver.collect_runtime())
        action = Action('click', Target(role='button', name='Trigger fault'))
        driver.set_runtime_context('t01-framework', 'ST-4', 'A-4', 'action')
        driver.execute(action)
        evidence = EvidenceEngine(OUTPUT / heading / 'artifacts').build_technical(
            RuntimeObserver().observe(driver, before), action, driver=driver, step_id='ST-4', action_id='A-4')[0]
    finally:
        driver.close()
    engine = ReplayEngine(OUTPUT / heading / 'replay')
    engine.save(evidence)
    result = engine.replay(evidence.id)
    (OUTPUT / heading / 'result.json').write_text(json.dumps(result.to_dict(), indent=2))
    assert result.status == 'reproduced', result.note


@pytest.mark.parametrize('entry', ['react.html', 'vue.html'])
def test_built_vite_entries_use_source_preflight_and_restore_owned_service(entry):
    from copy import deepcopy
    from alienqa.local_run import serve_project
    root = ROOT / 'examples/open-source/t02-frameworks'
    project = select_project(ProjectLoader(), str(root), 'vite')
    server, selected = serve_project(project, entry)
    assert selected == entry
    assert project.entry_points == ['vite/dist/' + entry]
    driver = PlaywrightDriver(browser='chromium')
    try:
        driver.launch(project.base_url)
        for action in [Action('type', Target(label='Email'), 'alienqa@example.com'),
                       Action('click', Target(role='button', name='Save')),
                       Action('click', Target(role='button', name='Details'))]:
            assert driver.execute(action)['status'] == 'completed'
        before = deepcopy(driver.collect_runtime())
        action = Action('click', Target(role='button', name='Trigger fault'))
        driver.set_runtime_context('t01-static', 'ST-4', 'A-4', 'action')
        driver.execute(action)
        evidence = EvidenceEngine(OUTPUT / entry / 'artifacts').build_technical(
            RuntimeObserver().observe(driver, before), action, driver=driver, step_id='ST-4', action_id='A-4')[0]
        evidence.replay['static_server'] = project.artifacts['static_server']
    finally:
        driver.close()
        server.shutdown()
        server.server_close()
    engine = ReplayEngine(OUTPUT / entry / 'replay')
    engine.save(evidence)
    result = engine.replay(evidence.id)
    (OUTPUT / entry / 'result.json').write_text(json.dumps(result.to_dict(), indent=2))
    assert result.status == 'reproduced', result.note
