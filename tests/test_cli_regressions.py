"""CLI input selection and partial-run behavior without browser/model calls."""
import json
from types import SimpleNamespace

import pytest

from alienqa import __main__ as cli
from alienqa.pipeline import PipelineResult


@pytest.fixture
def cli_rig(monkeypatch):
    calls = SimpleNamespace(project=None, kwargs=None, result=PipelineResult())

    class Pipeline:
        def __init__(self, config, **kwargs):
            calls.kwargs = kwargs
            self.client = SimpleNamespace()

        def collect(self, project):
            calls.project = project
            return calls.result

    monkeypatch.setattr(cli, "AlienQAPipeline", Pipeline)
    monkeypatch.setattr(cli, "_load_keys", lambda: None)
    monkeypatch.setattr(cli, "check_url", lambda url: url)
    monkeypatch.setattr(cli, "check_browser", lambda browser: None)
    return calls


def test_url_only_uses_black_box_and_saved_session(cli_rig, tmp_path):
    state = tmp_path / "session.json"
    state.write_text(json.dumps({"cookies": [], "origins": []}))
    code = cli.main(["--url", "https://app.test/", "--storage-state", str(state),
                     "--artifacts-dir", str(tmp_path / "artifacts")])
    assert code == 0
    assert cli_rig.project.input_type == "browser"
    assert cli_rig.project.visible_files == []
    assert cli_rig.project.storage_state == str(state)
    assert cli_rig.kwargs["auto_confirm"] is False


def test_source_with_url_uses_real_loader(cli_rig, tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "18", "react-dom": "18"}}))
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    code = cli.main(["--project-root", str(tmp_path), "--url", "http://localhost:5173",
                     "--artifacts-dir", str(tmp_path / "artifacts")])
    assert code == 0
    assert cli_rig.project.framework == "React"
    assert cli_rig.project.root == str(tmp_path)
    assert cli_rig.project.base_url == "http://localhost:5173"


def test_missing_session_is_an_input_error(cli_rig, tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--url", "https://app.test/", "--storage-state", str(tmp_path / "missing.json")])
    assert exc.value.code == 2


def test_partial_scan_has_nonzero_exit_and_diagnostics(cli_rig, tmp_path):
    cli_rig.result = PipelineResult(steps=[{"status": "failed", "error": "judge failed"}])
    artifact_dir = tmp_path / "artifacts"
    code = cli.main(["--url", "https://app.test/", "--artifacts-dir", str(artifact_dir)])
    assert code == 2
    saved = json.loads((artifact_dir / "scan.json").read_text())
    assert saved["incomplete"] is True
    assert saved["steps"][0]["error"] == "judge failed"


def test_ctrl_c_preserves_committed_prefix(cli_rig, monkeypatch, tmp_path):
    from alienqa.run_writer import RunWriter, load_snapshot
    directory = tmp_path / "interrupted"
    def interrupted(self, project):
        RunWriter(directory, directory.name).checkpoint(phase="visual", steps=[{
            "status": "inconclusive", "cognitive_status": "pending"}], evidences=[], diagnostics=[])
        raise KeyboardInterrupt()
    monkeypatch.setattr(cli.AlienQAPipeline, "collect", interrupted)
    assert cli.main(["--url", "https://app.test/", "--artifacts-dir", str(directory)]) == 130
    saved = load_snapshot(directory)
    assert saved["stop_reason"] == "cancelled"
    assert len(saved["steps"]) == 1 and saved["steps"][0]["cognitive_status"] == "inconclusive"


@pytest.mark.skipif(cli.os.name != "posix", reason="POSIX process-group lifecycle")
def test_stop_app_kills_descendants_after_wrapper_exits(monkeypatch):
    import signal

    signals = []
    process = SimpleNamespace(pid=123456, wait=lambda timeout: 0)
    monkeypatch.setattr(cli.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    cli._stop_app(process)
    assert signals == [(process.pid, signal.SIGTERM), (process.pid, signal.SIGKILL)]


def test_source_start_command_is_ready_then_stopped(cli_rig, tmp_path):
    import socket
    import sys

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "18", "react-dom": "18"}}))
    (tmp_path / "index.html").write_text("<p>Running application</p>")
    code = cli.main([
        "--project-root", str(tmp_path), "--url", f"http://127.0.0.1:{port}/",
        "--start-command", f"{sys.executable} -m http.server {port} --bind 127.0.0.1",
        "--startup-timeout", "5", "--artifacts-dir", str(tmp_path / "artifacts"),
    ])
    assert code == 0 and cli_rig.project.framework == "React"
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_exited_start_command_does_not_run_scan(cli_rig, tmp_path):
    import sys

    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "18", "react-dom": "18"}}))
    (tmp_path / "index.html").write_text("<p>Application</p>")
    code = cli.main([
        "--project-root", str(tmp_path), "--url", "http://127.0.0.1:9/",
        "--start-command", f"{sys.executable} -c 'raise SystemExit(1)'",
        "--startup-timeout", "2", "--artifacts-dir", str(tmp_path / "artifacts"),
    ])
    assert code == 1 and cli_rig.project is None


def test_cli_review_passes_persistent_path_and_partial_diagnostics(cli_rig, monkeypatch, tmp_path):
    applications = []
    create_review_app = cli.create_app

    def create_without_server(*args, **kwargs):
        app = create_review_app(*args, **kwargs)
        app.run = lambda **options: None
        applications.append(app)
        return app

    monkeypatch.setattr(cli, "create_app", create_without_server)
    cli_rig.result = PipelineResult(steps=[{"index": 1, "status": "failed", "error": "model failure"}])
    code = cli.main(["--url", "https://app.test/", "--review", "--artifacts-dir", str(tmp_path)])
    assert code == 2
    assert applications[0].config["diagnostics"][0]["error"] == "model failure"
    assert (tmp_path / "review.json").is_file()


def test_cli_default_analysis_preserves_pending_and_mode_paths(cli_rig, tmp_path):
    from alienqa.evidence import Evidence
    cli_rig.result = PipelineResult(evidences=[Evidence(id="EV", expectation="用户原声")])
    args = ["--url", "https://app.test/", "--artifacts-dir", str(tmp_path)]
    assert cli.main(args) == 0
    html = (tmp_path / "analysis.html").read_text()
    assert "用户原声" in html and "pending" in html
    assert not (tmp_path / "report.html").exists()
    assert json.loads((tmp_path / "review.json").read_text()) == {}
    assert cli.main(args + ["--report-mode", "confirmed"]) == 1
    assert not (tmp_path / "report.html").exists()
    demo = tmp_path / "explicit-demo"
    assert cli.main(args + ["--artifacts-dir", str(demo), "--report-mode", "confirmed", "--auto-confirm"]) == 0
    assert "未经人工审核" in (demo / "report.html").read_text()


def test_cli_explicit_output_wins(cli_rig, tmp_path):
    output = tmp_path / "custom" / "qa.html"
    directory = tmp_path / "run"
    assert cli.main(["--url", "https://app.test/", "--artifacts-dir", str(directory), "--output", str(output)]) == 0
    assert output.is_file() and not (directory / "analysis.html").exists()
    assert "未记录发现" in output.read_text()


def test_cli_rejects_invalid_report_mode():
    with pytest.raises(SystemExit) as exc:
        cli.main(["--report-mode", "invalid"])
    assert exc.value.code == 2


@pytest.mark.parametrize("interrupted", [False, True])
def test_corrupt_metering_never_blocks_report_or_committed_prefix(cli_rig, monkeypatch, tmp_path, capsys, interrupted):
    from alienqa.run_writer import RunWriter, load_snapshot

    def collect(self, project):
        directory = tmp_path / "llm" / "calls"
        directory.mkdir(parents=True)
        (directory / "broken.json").write_text("broken")
        if interrupted:
            RunWriter(tmp_path, tmp_path.name).checkpoint(phase="visual", steps=[{
                "status": "inconclusive", "cognitive_status": "pending"}], evidences=[], diagnostics=[])
            raise KeyboardInterrupt()
        return cli_rig.result

    monkeypatch.setattr(cli.AlienQAPipeline, "collect", collect)
    code = cli.main(["--url", "https://app.test/", "--artifacts-dir", str(tmp_path)])
    assert code == (130 if interrupted else 0)
    assert "计量" in capsys.readouterr().err
    saved = load_snapshot(tmp_path)
    if interrupted:
        assert saved["stop_reason"] == "cancelled"
    else:
        html = (tmp_path / "analysis.html").read_text()
        assert "未记录发现" in html and "corrupt" in html


def test_selected_app_controls_source_and_start_command_cwd(cli_rig, tmp_path):
    import socket
    import sys
    for name in ('web', 'admin'):
        app = tmp_path / 'apps' / name
        app.mkdir(parents=True)
        (app / 'package.json').write_text(json.dumps({'dependencies': {'react': '18', 'react-dom': '18'}}))
        (app / 'index.html').write_text(f'<p>{name}</p>')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    arguments = ['--project-root', str(tmp_path), '--url', f'http://127.0.0.1:{port}',
        '--artifacts-dir', str(tmp_path / 'scan'), '--unit', 'Save', '--instructions', 'Top right']
    with pytest.raises(SystemExit) as error:
        cli.main(arguments)
    assert error.value.code == 2
    command = f'''{sys.executable} -c 'from pathlib import Path; import http.server; Path("started-cwd").write_text(str(Path.cwd())); http.server.test(HandlerClass=http.server.SimpleHTTPRequestHandler, port={port}, bind="127.0.0.1")' '''
    assert cli.main(arguments + ['--app', 'apps/web', '--start-command', command]) == 0
    selected = tmp_path / 'apps/web'
    assert cli_rig.project.root == str(tmp_path)
    assert cli_rig.project.app_dir == str(selected)
    assert (selected / 'started-cwd').read_text() == str(selected)
    assert not (tmp_path / 'apps/admin/started-cwd').exists()
    assert cli_rig.kwargs['unit'] == 'Save' and cli_rig.kwargs['instructions'] == 'Top right'
    with socket.socket() as probe:
        assert probe.connect_ex(('127.0.0.1', port)) != 0


def test_cli_static_build_uses_same_directory_as_console(cli_rig, tmp_path):
    from alienqa.ui.app import _prepare_project
    from alienqa.ui.runs import RunRecord
    from alienqa.loader import EntryDetector
    (tmp_path / 'package.json').write_text(json.dumps({'dependencies': {'react': '18', 'react-dom': '18'}}))
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<p>Built page</p>')
    assert cli.main(['--project-root', str(tmp_path), '--artifacts-dir', str(tmp_path / 'scan')]) == 0
    assert cli_rig.project.artifacts['static_server']['directory'] == str(dist)
    rec = RunRecord(id='test', project_path=str(tmp_path))
    project, server = _prepare_project(rec, EntryDetector())
    try:
        assert project.artifacts['static_server']['directory'] == str(dist)
        assert cli_rig.project.framework == project.framework
    finally:
        server.shutdown()
        server.server_close()


def test_cli_static_deployment_and_default_entry_match_console(cli_rig, tmp_path):
    from alienqa.ui.app import _prepare_project
    from alienqa.ui.runs import RunRecord, RunManager
    (tmp_path / 'web.html').write_text('<p>Mounted site</p>')
    output = tmp_path / 'scan'
    assert cli.main(['--project-root', str(tmp_path), '--base-path', '/tool', '--spa-fallback',
                     '--artifacts-dir', str(output)]) == 0
    metadata = cli_rig.project.artifacts['static_server']
    assert metadata['entry'] == 'web.html' and metadata['spa_fallback'] == 'web.html'
    assert cli_rig.project.base_url.endswith('/tool/web.html')
    saved = RunManager(tmp_path).get('scan')
    assert saved.source_context['artifacts']['static_server'] == metadata
    assert saved.source_context['environment']['base_url_status'] == 'actual_static_service'
    rec = RunRecord(id='console', project_path=str(tmp_path), entry='', base_path='/tool/', spa_fallback=True)
    project, server = _prepare_project(rec, None)
    try:
        actual = project.artifacts['static_server']
        assert {k: v for k, v in actual.items() if k != 'port'} == {k: v for k, v in metadata.items() if k != 'port'}
    finally:
        server.shutdown()
        server.server_close()
