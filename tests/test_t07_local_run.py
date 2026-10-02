"""Shared local input, authoritative completion and readable history contracts."""
import json

import pytest

from alienqa.run_writer import RunWriter, load_snapshot
from alienqa.ui.app import _complete_scan
from alienqa.ui.runs import RunManager


@pytest.mark.parametrize('field,value', [('max_actions', 0), ('max_actions', True), ('samples', 1.5),
    ('max_seconds', float('nan')), ('max_seconds', float('inf')), ('startup_timeout', -1)])
def test_shared_input_rejects_invalid_budgets(field, value):
    from alienqa.local_run import ScanInput
    with pytest.raises(ValueError):
        ScanInput.from_dict({'url': 'http://localhost:8000', field: value})


@pytest.mark.parametrize('url', ['http://:8000', 'http://localhost:0', 'http://localhost:99999',
                                  'http://user:secret@localhost', 'file:///etc/passwd'])
def test_shared_input_rejects_malformed_or_credential_url(url):
    from alienqa.local_run import ScanInput
    with pytest.raises(ValueError):
        ScanInput.from_dict({'url': url})


def test_session_entry_validation_does_not_echo_secrets(tmp_path):
    from alienqa.local_run import ScanInput
    session = tmp_path / 'session.json'
    session.write_text(json.dumps({'cookies': [{'value': 'PRIVATE_COOKIE'}], 'origins': []}))
    with pytest.raises(ValueError) as error:
        ScanInput.from_dict({'url': 'http://localhost', 'storage_state': str(session)})
    assert 'PRIVATE_COOKIE' not in str(error.value)


def test_terminal_completion_is_derived_from_committed_prefix(tmp_path):
    runs = RunManager(tmp_path)
    rec = runs.create('http://localhost', mode='browser')
    RunWriter(rec.dir, rec.id).checkpoint(phase='terminal', steps=[], evidences=[], diagnostics=[{'error': 'model failed'}])
    (rec.dir / 'completion.json').write_text(json.dumps({'status': 'done', 'evidence_count': 999, 'issue_count': 999}))
    from types import SimpleNamespace
    app = SimpleNamespace(config={'runs': runs, 'running': True})
    _complete_scan(app, rec.id, None)
    result = runs.get(rec.id)
    assert result.status == 'partial'
    assert result.evidence_count == result.issue_count == 0


def test_worker_done_without_terminal_checkpoint_is_error_and_preserves_prefix(tmp_path):
    runs = RunManager(tmp_path)
    rec = runs.create('http://localhost', mode='browser')
    RunWriter(rec.dir, rec.id).checkpoint(phase='visual', steps=[{'cognitive_status': 'pending'}], evidences=[], diagnostics=[])
    (rec.dir / 'completion.json').write_text('{"status":"done"}')
    from types import SimpleNamespace
    app = SimpleNamespace(config={'runs': runs, 'running': True})
    _complete_scan(app, rec.id, None)
    assert runs.get(rec.id).status == 'error'
    saved = load_snapshot(rec.dir)
    assert saved['stop_reason'] == 'error' and len(saved['steps']) == 1
    assert saved['last_stage'] == 'visual'
    assert saved['steps'][0]['cognitive_status'] == 'inconclusive'


def test_read_summary_distinguishes_absent_corrupt_and_available(tmp_path):
    runs = RunManager(tmp_path)
    rec = runs.create('local')
    assert runs.summary(rec.id)['data_status'] == 'absent'
    RunWriter(rec.dir, rec.id).checkpoint(phase='terminal', steps=[
        {'execution': {'status': 'ok'}, 'cognitive_status': 'passed'},
        {'execution': {'status': 'failed'}, 'cognitive_status': 'inconclusive'}], evidences=[], diagnostics=[])
    summary = runs.summary(rec.id)
    assert summary['data_status'] == 'available'
    assert summary['attempts'] == 2 and summary['executions'] == 1
    assert summary['cognitive_completed'] == 1 and summary['inconclusive'] == 1
    (rec.dir / 'scan.json').write_text('{broken')
    assert runs.summary(rec.id)['data_status'] == 'corrupt'


def test_cli_review_run_reuses_saved_notes_without_scanning(tmp_path, monkeypatch):
    from alienqa import __main__ as cli
    from alienqa.review import Decision, HumanReview, ReviewState
    from alienqa.evidence import Evidence
    writer = RunWriter(tmp_path, tmp_path.name)
    writer.checkpoint(phase='terminal', steps=[], evidences=[Evidence(id='EV', expectation='Feedback')], diagnostics=[])
    state = ReviewState()
    state.decide('EV', Decision.BY_DESIGN, 'Keep my note')
    HumanReview(state).save(tmp_path / 'review.json')
    applications = []
    original = cli.create_app
    def capture(*args, **kwargs):
        app = original(*args, **kwargs)
        app.run = lambda **kwargs: None
        applications.append(app)
        return app
    monkeypatch.setattr(cli, 'create_app', capture)
    monkeypatch.setattr(cli, 'check_browser', lambda _: pytest.fail('review must not open a browser'))
    assert cli.main(['--review-run', str(tmp_path)]) == 0
    assert 'Keep my note' in applications[0].test_client().get('/').get_data(as_text=True)
    assert load_snapshot(tmp_path)['checkpoint_seq'] == 1


def test_selected_app_cannot_leave_repository(tmp_path):
    from alienqa.local_run import select_project
    from alienqa.loader import ProjectLoader
    (tmp_path / 'index.html').write_text('<p>App</p>')
    with pytest.raises(ValueError, match='内部'):
        select_project(ProjectLoader(), str(tmp_path), '..')


def test_preflight_rejects_missing_required_model_without_invocation():
    from alienqa.local_run import validate_config
    from alienqa.llm import LLMConfig
    with pytest.raises(ValueError, match='expectation'):
        validate_config(LLMConfig.from_dict({'roles': {'gist': {'model': 'test/gist'}}}))


def test_cli_invalid_url_matches_ui_before_scan(tmp_path):
    from alienqa import __main__ as cli
    from alienqa.ui import create_ui_app
    config = tmp_path / 'config.yaml'
    config.write_text('llm: {}')
    with pytest.raises(SystemExit) as error:
        cli.main(['--url', 'http://:8000'])
    assert error.value.code == 2
    app = create_ui_app(str(config), str(tmp_path / 'settings'), str(tmp_path / 'runs'))
    assert app.test_client().post('/api/run', json={'url': 'http://:8000'}).status_code == 400


def test_output_preflight_identifies_non_directory_without_models(tmp_path):
    from alienqa.local_run import check_output
    path = tmp_path / 'file'
    path.write_text('occupied')
    with pytest.raises(OSError):
        check_output(path)


def test_summary_unsupported_schema_is_not_empty_pass(tmp_path):
    runs = RunManager(tmp_path)
    rec = runs.create('local')
    (rec.dir / 'scan.json').write_text('{"schema_version":999}')
    assert runs.summary(rec.id)['data_status'] == 'unsupported'
