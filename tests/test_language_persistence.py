"""New scans remember language; pre-localization records stay compatible."""
import pytest

from alienqa.i18n import language_context
from alienqa.local_run import ScanInput
from alienqa.run_writer import RunWriter, load_snapshot
from alienqa.ui.runs import RunManager, RunRecord


def test_scan_language_uses_request_and_accepts_explicit_alias():
    with language_context('en'):
        assert ScanInput.from_dict({'url': 'https://example.com'}).language == 'en'
        assert ScanInput.from_dict({'url': 'https://example.com', 'language': 'zh-CN'}).language == 'zh'


def test_scan_rejects_unsupported_language():
    with pytest.raises(ValueError, match='Unsupported language'):
        ScanInput.from_dict({'url': 'https://example.com', 'language': 'fr'})


def test_run_language_roundtrip_and_old_record_default(tmp_path):
    runs = RunManager(tmp_path)
    record = runs.create('example', language='en')
    assert runs.get(record.id).language == 'en'
    assert RunRecord.from_dict({'id': 'legacy'}).language == 'zh'


def test_checkpoint_retains_language_after_terminal_diagnostic(tmp_path):
    writer = RunWriter(tmp_path, 'en-test')
    writer.checkpoint(phase='terminal', steps=[], evidences=[], diagnostics=[], language='en')
    writer.append_terminal_diagnostic('error', 'Worker failed')
    assert load_snapshot(tmp_path)['language'] == 'en'


def test_cancelled_run_before_first_checkpoint_keeps_language(tmp_path):
    runs = RunManager(tmp_path)
    record = runs.create('example', language='en')
    runs.append_terminal_diagnostic(record.id, 'cancelled', 'Scan cancelled')
    assert load_snapshot(record.dir)['language'] == 'en'


def test_english_validation_message():
    with language_context('en'), pytest.raises(ValueError, match='valid HTTP/HTTPS URL'):
        ScanInput.from_dict({'url': 'invalid'})
