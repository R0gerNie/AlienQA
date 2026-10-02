"""Real HTTP, Chromium and scan worker termination; no external model calls."""
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
from types import SimpleNamespace

import pytest

from alienqa.run_writer import load_snapshot
from alienqa.ui.jobs import JobController
from alienqa.ui.runs import RunManager


def _blocked_scan(config_path, runs_dir, run_id, block_role):
    from alienqa.llm import client
    from alienqa.ui.app import _scan_worker

    role_counts = {}

    def completion(**kwargs):
        role = kwargs['model'].split('/')[-1]
        role_counts[role] = role_counts.get(role, 0) + 1
        if role == block_role and (role != 'expectation' or role_counts[role] == 2):
            (Path(runs_dir) / run_id / 'blocked').write_text(role)
            time.sleep(120)  # deliberately interrupted by the real JobController
        content = kwargs['messages'][0]['content']
        prompt = content[0]['text'] if isinstance(content, list) else content
        if role == 'gist':
            text = '{"areas":[],"relations":[]}' if '产品地图' in prompt else 'A save page'
        elif role == 'expectation':
            text = json.dumps({'expectations': [{'text': 'Save should show feedback',
                         'expectation_basis': {'type': 'interaction_convention', 'reference': 'Submission needs feedback'}}]})
        elif role == 'visual':
            text = '{"changes":[],"summary":"No feedback"}'
        else:
            text = '{"status":"passed","mismatches":[]}'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=None)

    client._litellm = lambda: SimpleNamespace(completion=completion)
    _scan_worker(config_path, {}, runs_dir, run_id)


@pytest.fixture
def runtime_url():
    html = (Path(__file__).parent / 'fixtures/runtime-app/index.html').read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(html)

        def do_POST(self):
            self.send_response(503)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}/'
    server.shutdown()
    server.server_close()
    thread.join(2)


@pytest.mark.skipif(os.name != 'posix', reason='POSIX worker/browser process group')
@pytest.mark.parametrize('block_role', ['gist', 'expectation', 'visual', 'judge'])
def test_real_worker_cancel_preserves_committed_browser_prefix(runtime_url, tmp_path, block_role):
    from alienqa.ui.app import _complete_scan

    runs = RunManager(tmp_path / 'runs')
    url = runtime_url + ('?entry=1' if block_role in {'gist', 'expectation'} else '')
    rec = runs.create(url, mode='browser', base_url=url)
    config = tmp_path / 'config.yaml'
    config.write_text(json.dumps({'llm': {'roles': {
        role: {'model': f'test/{role}'} for role in ['gist', 'expectation', 'visual', 'judge', 'investigator', 'reporter']}}}))
    app = SimpleNamespace(config={'runs': runs, 'running': True})
    jobs = JobController()
    token = jobs.reserve()
    finished = threading.Event()
    outcomes = []

    def complete(status):
        outcomes.append(status)
        _complete_scan(app, rec.id, status)
        finished.set()

    jobs.start(token, rec.id, _blocked_scan, (str(config), str(runs.root), rec.id, block_role),
               complete, timeout=30)
    try:
        deadline = time.monotonic() + 15
        while not (rec.dir / 'blocked').exists() and time.monotonic() < deadline:
            time.sleep(0.03)
        assert (rec.dir / 'blocked').exists(), runs.load_diagnostics(rec.id)
        before = load_snapshot(rec.dir)
        usage_before = runs.load_usage(rec.id)
        assert usage_before['counts']['started'] == 1
        assert len(before['evidences']) == (1 if block_role in {'gist', 'expectation'} else 2)
        if block_role == 'expectation':
            step = before['steps'][0]
            assert step['execution_status'] == 'not_started'
            assert step['input']['cognitive']['step_id'] == step['step_id']
            generation = step['expectation_generation']
            assert len([sample for sample in generation['samples'] if sample.get('status') == 'validated']) == 1
            assert generation['sampling'] == {'requested': 2, 'returned': 1, 'validated': 1, 'complete': False}
            assert generation['samples'][-1]['status'] == 'started'
        if block_role in {'visual', 'judge'}:
            windows = [r for ref in before['raw_refs'] for r in
                       json.loads((rec.dir / ref['path']).read_text())['records']]
            errors = [r for r in windows if r['kind'] == 'http_response' and r['payload']['status'] == 503]
            assert len(errors) == 2
            assert errors[0]['record_id'] != errors[1]['record_id']
        assert jobs.cancel(rec.id)
        assert finished.wait(8)
        assert outcomes == ['cancelled']
        restarted = RunManager(runs.root)
        assert restarted.get(rec.id).status == 'cancelled'
        assert restarted.get(rec.id).evidence_count == len(before['evidences'])
        assert len(restarted.load_evidences(rec.id)) == len(before['evidences'])
        assert restarted.load_diagnostics(rec.id)['incomplete'] is True
        usage = restarted.load_usage(rec.id)
        assert usage['attempts'] == usage_before['attempts']
        assert usage['counts']['unknown'] == 1 and usage['counts']['started'] == 0
        assert usage['unknown_cost_attempts'] == usage['attempts']
        assert usage['scan_accounting_recorded'] and not usage['complete']
        assert load_snapshot(rec.dir)['checkpoint_seq'] > before['checkpoint_seq']
        if block_role == 'expectation':
            generation = load_snapshot(rec.dir)['steps'][0]['expectation_generation']
            # Cooperative TERM records explicit cancellation; forced exit leaves incomplete.
            assert generation['samples'][-1]['status'] in {'cancelled', 'incomplete'}
            assert generation['sampling']['complete'] is False
        _complete_scan(app, rec.id, None)  # late success cannot overwrite cancellation
        assert restarted.get(rec.id).status == 'cancelled'
    finally:
        if not finished.is_set():
            jobs.cancel(rec.id)
            finished.wait(8)
