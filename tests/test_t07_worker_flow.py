"""Real workers, Chromium, CLI, replay and reports; offline model executable only."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from alienqa import __main__ as cli
from alienqa.run_writer import load_snapshot
from alienqa.ui import create_ui_app
from alienqa.ui.runs import RunManager

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def rig(monkeypatch):
    directory = REPO / 'artifacts/evaluation/t07-worker' / uuid.uuid4().hex
    directory.mkdir(parents=True)
    temp = directory / 'tmp'
    temp.mkdir()
    monkeypatch.setenv('TMPDIR', str(temp))
    # tempfile's cached directory must also remain inside the project.
    import tempfile
    monkeypatch.setattr(tempfile, 'tempdir', str(temp))
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', str(REPO / '.venv/browsers'))
    executable = directory / 'offline-model'
    executable.write_text(f'#!{sys.executable}\n' + (REPO / 'tests/fixtures/t07-model-provider.py').read_text())
    executable.chmod(0o700)
    config = directory / 'config.yaml'
    config.write_text(json.dumps({'llm': {'request_timeout': 30, 'codex': {'executable': str(executable)},
        'roles': {role: {'model': f'codex/{role}'} for role in ('gist', 'expectation', 'visual', 'judge', 'investigator', 'reporter')}}}))
    yield directory, config, executable


@pytest.fixture
def website():
    html = (REPO / 'tests/fixtures/runtime-app/index.html').read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith('/private') and 'session=local-only' not in self.headers.get('Cookie', ''):
                self.send_response(302)
                self.send_header('Location', '/login')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<p>Please log in</p>' if self.path == '/login' else html)
        def do_POST(self):
            self.send_response(503)
            self.end_headers()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def wait_until(check, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(.05)
    pytest.fail('Local worker condition did not complete')


def test_real_worker_browser_review_replay_export_restart(rig, website):
    directory, config, _ = rig
    app = create_ui_app(str(config), str(directory / 'settings'), str(directory / 'runs'))
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            tab = browser.new_page()
            tab.goto(base)
            tab.locator('#base_url').fill(website + '/')
            tab.locator('#max_actions').fill('1')
            tab.get_by_text('高级输入', exact=True).click()
            tab.locator('#samples').fill('1')
            tab.locator('#browser').select_option('chromium')
            with tab.expect_response(lambda response: response.url == base + '/api/run' and response.request.method == 'POST') as started:
                tab.get_by_role('button', name='开始扫描').click()
            assert started.value.status == 200
            run_id = started.value.json()['run_id']
            runs = app.config['runs']
            rec = wait_until(lambda: runs.get(run_id) if runs.get(run_id).status != 'running' else None)
            assert rec.status == 'done'
            summary = runs.summary(run_id)
            assert summary['attempts'] == summary['executions'] == summary['cognitive_completed'] == 1
            assert summary['technical_findings'] >= 2 and summary['cognitive_findings'] == 1
            assert summary['budget'] == {'samples': 1, 'max_actions': 1, 'max_seconds': 300}
            assert summary['access_result']['actual_url'] == website + '/'
            evidences = runs.load_evidences(run_id)
            technical = next(e for e in evidences if e.finding_kind == 'technical_anomaly' and 'exception' in e.observation_summary)
            tab.goto(base + f'/runs/{run_id}/review')
            with tab.expect_response(lambda response: '/replay/' in response.url and response.request.method == 'POST') as replay:
                tab.locator(f'.replay[data-id="{technical.id}"]').click()
            assert replay.value.status == 202
            wait_until(lambda: runs.load_replay_results(run_id).get(technical.id, {}).get('status') != 'running')
            assert runs.load_replay_results(run_id)[technical.id]['status'] == 'reproduced'
            row = tab.locator('[data-review]').first
            selected = row.get_attribute('data-review')
            row.locator('select').select_option('by-design')
            row.locator('textarea').fill('Deliberate product choice')
            row.get_by_role('button', name='保存决定').click()
            expect(row.locator('[role="status"]')).to_contain_text('已保存')
            assert tab.request.get(base + f'/runs/{run_id}/report?mode=confirmed').status == 409
            with tab.expect_download() as download:
                tab.get_by_role('link', name='下载分析', exact=True).click()
            offline = directory / 'export/analysis.html'
            offline.parent.mkdir()
            download.value.save_as(offline)
            tab.goto(offline.as_uri())
            expect(tab.locator('body')).to_contain_text('Deliberate product choice')
            expect(tab.locator('body')).to_contain_text('Save should show feedback')
            # Restart readers recover facts, decisions and replay results.
            restarted = create_ui_app(str(config), str(directory / 'settings'), str(directory / 'runs'))
            assert restarted.config['runs'].load_review(run_id).note(selected) == 'Deliberate product choice'
            for ev in evidences:
                response = restarted.test_client().post(f'/runs/{run_id}/decide', json={
                    'evidence_id': ev.id, 'decision': 'confirmed' if ev.id == technical.id else 'rejected', 'note': 'reviewed'})
                assert response.status_code == 200, response.get_json()
            assert not (rec.dir / 'analysis.html').exists()
            confirmed = restarted.test_client().get(f'/runs/{run_id}/report?mode=confirmed')
            assert confirmed.status_code == 200
            assert restarted.config['runs'].summary(run_id)['confirmed'] == 1
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.parametrize('termination', ['cancelled', 'timeout'])
def test_real_worker_blocked_cli_provider_is_stopped_with_prefix(rig, website, monkeypatch, termination):
    import importlib
    module = importlib.import_module('alienqa.ui.app')
    directory, config, executable = rig
    data = json.loads(config.read_text())
    data['llm']['roles']['gist']['model'] = 'codex/gist-block'
    config.write_text(json.dumps(data))
    monkeypatch.setattr(module, 'JOB_TIMEOUT_SECONDS', 7)
    app = create_ui_app(str(config), str(directory / 'settings'), str(directory / 'runs'))
    client = app.test_client()
    response = client.post('/api/run', json={'url': website + '/?entry=1', 'browser': 'chromium', 'max_actions': 1})
    assert response.status_code == 200
    run_id = response.json['run_id']
    wait_until(lambda: executable.with_suffix('.blocked').exists(), timeout=7)
    pid = int(executable.with_suffix('.blocked').read_text())
    if termination == 'cancelled':
        assert client.post(f'/api/run/{run_id}/stop').status_code == 202
    runs = app.config['runs']
    rec = wait_until(lambda: runs.get(run_id) if runs.get(run_id).status != 'running' else None)
    assert rec.status == termination
    snapshot = load_snapshot(rec.dir)
    assert snapshot['stop_reason'] == termination and snapshot['evidences']
    assert all(row['finding_kind'] == 'technical_anomaly' for row in snapshot['evidences'])
    assert runs.summary(run_id)['cognitive_completed'] == 0
    # This model executable owns a separate process group; it must not be orphaned.
    def exited():
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        return False
    try:
        assert wait_until(exited, timeout=3)
    finally:
        if not exited():
            os.killpg(pid, 9)
    restarted = RunManager(directory / 'runs')
    assert restarted.load_evidences(run_id)
    assert app.config['job_controller'].reserve() is not None


def test_real_cli_session_and_redirect_are_recorded(rig, website):
    directory, config, _ = rig
    session = directory / 'session.json'
    session.write_text(json.dumps({'cookies': [{'name': 'session', 'value': 'local-only',
        'domain': '127.0.0.1', 'path': '/', 'httpOnly': True, 'secure': False, 'sameSite': 'Lax'}],
        'origins': [{'origin': website, 'localStorage': [{'name': 'notice', 'value': 'ready'}]}]}))
    for name, arguments, actual in [('redirect', [], website + '/login'),
                                     ('protected', ['--storage-state', str(session)], website + '/private')]:
        output = directory / name
        code = cli.main(['--config', str(config), '--url', website + '/private', '--browser', 'chromium',
                         '--samples', '1', '--max-actions', '1', '--artifacts-dir', str(output)] + arguments)
        assert code == (2 if name == 'redirect' else 0)
        snapshot = load_snapshot(output)
        assert snapshot['access_result']['actual_url'] == actual
        assert snapshot['access_result']['authentication'] == 'unverified'
        assert (output / 'analysis.html').exists()
