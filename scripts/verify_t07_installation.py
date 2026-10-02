"""Install an existing wheel in an empty project-local directory and run T07.

No dependency downloads or real model calls. Runtime dependencies come from the
invoking Python environment; this does not certify a fresh dependency install.
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

REPO = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def request(url, data=None, expected=200):
    payload = json.dumps(data).encode() if data is not None else None
    try:
        with urlopen(Request(url, data=payload, headers={'Content-Type': 'application/json'}), timeout=10) as response:
            body, status = response.read(), response.status
    except HTTPError as response:
        body, status = response.read(), response.code
    assert status == expected, (status, body[:300])
    return body


def wait(check, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (URLError, ConnectionError):
            pass
        time.sleep(.1)
    raise TimeoutError('installed local run did not complete')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', required=True)
    parser.add_argument('--fixtures', default=str(REPO / 'tests/fixtures'))
    parser.add_argument('--browser-path', default=os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or str(REPO / '.venv/browsers'))
    parser.add_argument('--output-root', default=str(REPO / 'artifacts/evaluation/t07-installation'))
    args = parser.parse_args(argv)
    fixtures = Path(args.fixtures).resolve()
    output_root = Path(args.output_root).resolve()
    if not output_root.is_relative_to(REPO / 'artifacts'):
        parser.error('Installation outputs must stay inside project artifacts')
    wheel = Path(args.wheel).resolve()
    root = output_root / uuid.uuid4().hex
    work, site = root / 'work', root / 'site'
    work.mkdir(parents=True)
    temp = work / 'tmp'
    temp.mkdir()
    env = {**os.environ, 'PYTHONPATH': str(site), 'TMPDIR': str(temp),
           'PLAYWRIGHT_BROWSERS_PATH': str(Path(args.browser_path).resolve())}
    processes = []
    logs = []
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    website = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(fixtures / 'runtime-app')))
    thread = threading.Thread(target=website.serve_forever, daemon=True)
    thread.start()
    target = f'http://127.0.0.1:{website.server_port}/'
    try:
        with (root / 'install.log').open('w') as log:
            subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', '--target', str(site), str(wheel)],
                           cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        assert (site / 'share/alienqa/config.yaml').is_file()
        package_path = subprocess.check_output([sys.executable, '-c', 'import alienqa; print(alienqa.__file__)'], cwd=work, env=env, text=True).strip()
        assert Path(package_path).is_relative_to(site)
        executable = work / 'offline-model'
        executable.write_text(f'#!{sys.executable}\n' + (fixtures / 't07-model-provider.py').read_text())
        executable.chmod(0o700)
        config = work / 'config.json'
        config.write_text(json.dumps({'llm': {'codex': {'executable': str(executable)}, 'roles': {
            role: {'model': f'codex/{role}'} for role in ('gist', 'expectation', 'visual', 'judge', 'investigator', 'reporter')}}}))
        common = [sys.executable, '-m', 'alienqa', '--config', str(config)]
        cli_run = work / 'runs/cli-scan'
        with (root / 'cli.log').open('w') as log:
            subprocess.run(common + ['--url', target, '--browser', 'chromium', '--samples', '1', '--max-actions', '1',
                '--artifacts-dir', str(cli_run)], cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
        def launch(arguments, name):
            log = (root / name).open('w')
            logs.append(log)
            process = subprocess.Popen(common + arguments, cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=(os.name == 'posix'))
            processes.append(process)
            return process
        base = f'http://127.0.0.1:{free_port()}'
        launch(['--ui', '--port', base.rsplit(':', 1)[1]], 'ui.log')
        wait(lambda: request(base))
        started = json.loads(request(base + '/api/run', {'url': target, 'browser': 'chromium', 'samples': 1, 'max_actions': 1}))
        run_id = started['run_id']
        def finished():
            result = json.loads(request(base + f'/api/run/{run_id}'))
            return result if result['status'] != 'running' else None
        status = wait(finished)
        assert status['status'] == 'done', status
        assert status['progress']['cognitive_findings'] == 1 and status['progress']['technical_findings'] >= 1
        run = work / 'runs' / run_id
        snapshot = json.loads((run / 'scan.json').read_text())
        evidence = next(row for row in snapshot['evidences'] if row['finding_kind'] == 'technical_anomaly')
        request(base + f'/api/run/{run_id}/replay/{evidence["id"]}', {}, expected=202)
        def replayed():
            result = json.loads(request(base + f'/api/run/{run_id}/replays'))[evidence['id']]
            return result if result['status'] != 'running' else None
        replay = wait(replayed)
        assert replay['status'] == 'reproduced', replay
        request(base + f'/runs/{run_id}/report?mode=confirmed', expected=409)
        for row in snapshot['evidences']:
            request(base + f'/runs/{run_id}/decide', {'evidence_id': row['id'],
                'decision': 'confirmed' if row['id'] == evidence['id'] else 'rejected', 'note': 'Installed package review'})
        html = request(base + f'/runs/{run_id}/report?mode=analysis&download=1')
        assert b'Installed package review' in html
        request(base + f'/runs/{run_id}/report?mode=confirmed&download=1')
        export = work / 'export/analysis.html'
        export.parent.mkdir()
        export.write_bytes(html)
        from playwright.sync_api import sync_playwright
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = env['PLAYWRIGHT_BROWSERS_PATH']
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            page = browser.new_page()
            page.goto(export.as_uri())
            assert 'Installed package review' in page.inner_text('body')
            assert page.locator('img').count() and page.locator('img').first.evaluate('(image) => image.complete && image.naturalWidth > 0')
            browser.close()
        review_base = f'http://127.0.0.1:{free_port()}'
        launch(['--review-run', str(run), '--port', review_base.rsplit(':', 1)[1]], 'review.log')
        assert b'Installed package review' in wait(lambda: request(review_base))
        assert b'Installed package review' in request(review_base + '/report?mode=analysis')
        result = {'wheel': str(wheel), 'import_path': package_path, 'python': sys.version, 'root': str(root),
                  'cli': 'passed', 'real_worker_ui': 'passed', 'replay': replay['status'], 'restart_review': 'passed',
                  'offline_html': 'passed', 'scan_counts': status['progress'], 'real_model_calls': 0,
                  'dependency_install': 'existing invoking environment; no dependency downloads'}
        (root / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(root)
        return 0
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for log in logs:
            log.close()
        website.shutdown()
        website.server_close()
        thread.join(2)


if __name__ == '__main__':
    raise SystemExit(main())
