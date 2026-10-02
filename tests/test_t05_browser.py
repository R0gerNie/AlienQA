"""Real independent contexts, restored history entry, auth and navigation fallback."""
from copy import deepcopy
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from alienqa.driver import Action, PlaywrightDriver, Target
from alienqa.evidence import Evidence, EvidenceEngine
from alienqa.observation.models import Observation
from alienqa.observation.runtime_observer import RuntimeObserver
from alienqa.replay import ReplayEngine
from alienqa.replay.engine import _ReplayHandler


@pytest.mark.parametrize('mode', ['entry', 'target'])
def test_real_source_specific_replay_without_image(http_base_url, tmp_path, mode):
    driver = PlaywrightDriver(browser='chromium', viewport={'width': 960, 'height': 720})
    try:
        driver.launch(http_base_url + '/replay-app/t05.html?mode=' + mode)
        driver.wait_for_settle()
        before = None
        target = None
        if mode == 'target':
            for action in [Action('type', Target(selector='#name'), 'Alien'), Action('click', Target(selector='#prepare'))]:
                driver.execute(action)
            before = deepcopy(driver.collect_runtime())
            driver.set_runtime_context('original', 'ST-3', 'A-3', 'action')
            target = Action('click', Target(selector='#target'))
            driver.execute(target)
        runtime = RuntimeObserver().observe(driver, before)
        evidence = EvidenceEngine(tmp_path / 'artifacts').build_technical(
            runtime, target, driver=driver, step_id='ST-3' if target else None, action_id='A-3' if target else None)[0]
    finally:
        driver.close()
    engine = ReplayEngine(tmp_path / 'replay')
    engine.save(evidence)
    result = engine.replay(evidence.id)
    assert result.status == 'reproduced', result.note
    assert result.preconditions['environment_applied'] is True
    assert result.preconditions['viewport'] == {'width': 960, 'height': 720}
    assert result.matched_basis[0]['source_record_id'] in evidence.source_record_ids
    assert len(result.executed_steps) == (3 if mode == 'target' else 0)


def test_spa_fallback_only_for_navigation_and_owned_server_cleanup(tmp_path):
    app = tmp_path / 'app'
    app.mkdir()
    (app / 'index.html').write_text('<button id="save" onclick="this.textContent=\'Saved\'">Save</button>')
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(_ReplayHandler, directory=str(app), spa_fallback=True))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    origin = f'http://127.0.0.1:{port}'
    driver = PlaywrightDriver(browser='chromium')
    try:
        for path, headers in [('/missing.js', {'Sec-Fetch-Dest': 'document'}), ('/api/missing', {'Sec-Fetch-Dest': 'document'}),
                              ('/deep/route', {'Accept': 'text/html'}), ('/deep/route', {'Sec-Fetch-Dest': 'script'})]:
            with pytest.raises(HTTPError) as failure:
                urlopen(Request(origin + path, headers=headers))
            assert failure.value.code == 404
        driver.launch(origin + '/deploy/deep?q=1#tab')
        driver.execute(Action('click', Target(selector='#save')))
        replay, after = driver.replay_data(), driver.screenshot()
    finally:
        driver.close()
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    replay['static_server'] = {'directory': str(app), 'port': port, 'spa_fallback': True}
    image = tmp_path / 'after.png'
    image.write_bytes(after)
    engine = ReplayEngine(tmp_path / 'replay')
    engine.save(Evidence(id='EV-spa', replay=replay, artifacts={'after': str(image)}))
    result = engine.replay('EV-spa')
    assert result.status == 'reproduced', result.note
    assert replay['url'].endswith('/deploy/deep?q=1#tab')
    probe = ThreadingHTTPServer(('127.0.0.1', port), _ReplayHandler)
    probe.server_close()


def test_expired_auth_and_external_service_remain_distinct_from_clean_pass(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        authenticated = True
        def log_message(self, *args):
            pass
        def do_GET(self):
            if self.path == '/protected' and not self.authenticated:
                self.send_response(302); self.send_header('Location', '/login'); self.end_headers()
            else:
                self.send_response(200); self.end_headers(); self.wfile.write(b'<h1>Home</h1>')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    driver = PlaywrightDriver(browser='chromium')
    try:
        driver.launch(origin + '/protected')
        replay = driver.replay_data()
        driver.close()
        Handler.authenticated = False
        engine = ReplayEngine(tmp_path)
        engine.save(Evidence(id='EV-auth', replay=replay))
        result = engine.replay('EV-auth')
        assert result.status == 'failed' and result.phase == 'access'
        assert '认证' in result.note
        with urlopen(origin + '/login') as response:
            assert response.status == 200  # replay never closes this external service
    finally:
        driver.close()
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_unsupported_scope_is_target_failure(http_base_url, tmp_path):
    engine = ReplayEngine(tmp_path)
    engine.save(Evidence(id='EV-scope', replay={'url': http_base_url + '/replay-app/t05.html', 'browser_kind': 'chromium',
        'package_version': 2, 'target_window': {'phase': 'action', 'step_id': 'ST-7'},
        'target_action': {'type': 'click', 'target': {'selector': '#target', 'scope': {'kind': 'closed_shadow'}}}}))
    result = engine.replay('EV-scope')
    assert result.status == 'failed' and result.phase == 'target'
    assert result.interrupted_step_id == 'ST-7'
