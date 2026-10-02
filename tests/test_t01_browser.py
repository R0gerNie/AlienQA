"""Actual deployment deep links and owned service restoration, without models."""
from copy import deepcopy
from pathlib import Path

import pytest

from alienqa.driver import Action, PlaywrightDriver, Target
from alienqa.evidence import EvidenceEngine
from alienqa.loader import Project
from alienqa.local_run import serve_project
from alienqa.observation.runtime_observer import RuntimeObserver
from alienqa.replay import ReplayEngine


@pytest.mark.parametrize('route', ['profile?tab=2#summary', 'index.html?tab=2#/profile'])
def test_mounted_deep_link_refresh_fault_and_independent_replay(tmp_path, route):
    root = Path(__file__).parent / 'fixtures/framework-mechanisms/deployment'
    project = Project(root=str(root))
    server, entry = serve_project(project, base_path='/tool/', spa_fallback=True)
    url = project.base_url.removesuffix(entry) + route
    driver = PlaywrightDriver(browser='chromium')
    try:
        driver.launch(url)
        assert driver._page.locator('h1').inner_text() == 'Mounted profile'
        driver._page.reload()
        assert driver._page.url == url
        driver.execute(Action('type', Target(label='Name'), 'Alien'))
        driver.execute(Action('click', Target(role='button', name='Save')))
        assert driver._page.get_by_role('status').inner_text() == 'Saved Alien'
        before = deepcopy(driver.collect_runtime())
        action = Action('click', Target(role='button', name='Trigger fault'))
        driver.set_runtime_context('t01', 'ST-3', 'A-3', 'action')
        driver.execute(action)
        evidence = EvidenceEngine(tmp_path / 'artifacts').build_technical(
            RuntimeObserver().observe(driver, before), action, driver=driver, step_id='ST-3', action_id='A-3')[0]
        evidence.replay['static_server'] = project.artifacts['static_server']
    finally:
        driver.close()
        server.shutdown()
        server.server_close()
    engine = ReplayEngine(tmp_path / 'replay')
    engine.save(evidence)
    result = engine.replay(evidence.id)
    assert result.status == 'reproduced', result.note
    assert evidence.replay['url'] == url
    assert result.preconditions['static_service'] == 'restored_owned'
