import json
import sqlite3

from alienqa.evidence import Evidence, EvidenceEngine, EvidenceStore
from alienqa.observation import RuntimeObservation


def test_old_sqlite_migrates_without_fabricating_basis(tmp_path):
    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE evidence (id TEXT PRIMARY KEY, action TEXT, expectation TEXT,
                    observation_summary TEXT, reasoning TEXT, severity TEXT, classification TEXT,
                    confidence REAL, timestamp TEXT, artifacts TEXT, replay TEXT)''')
        db.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   ('old', '{}', 'expect', 'observed', 'r', 'minor', 'other', 0.5, '', '{}', '{}'))
    store = EvidenceStore(path)
    old = store.get('old')
    assert old.expectation_basis is None and old.finding_kind is None
    assert old.run_id == '' and old.source_record_ids == []
    ev = Evidence(id='new', schema_version=2, finding_kind='cognitive_mismatch', run_id='run-1',
                  expectation_basis={'type': 'visible_copy', 'reference': 'Save'}, source_record_ids=['R-1'],
                  expectation_id='EX-ST-00001-001')
    store.insert(ev)
    assert store.get('new').to_dict() == ev.to_dict()


def test_new_run_default_store_does_not_overwrite_another_run(tmp_path):
    engines = [EvidenceEngine(tmp_path / name) for name in ['one', 'two']]
    for number, engine in enumerate(engines):
        ev = Evidence(id='EV-00001', finding_kind='technical_anomaly', run_id=str(number), confidence=None)
        engine.persist(ev)
    assert [engine.store.get('EV-00001').run_id for engine in engines] == ['0', '1']
    assert engines[0].store.get('EV-00001').confidence is None


def test_4xx_console_and_cancelled_requests_are_signals_only(tmp_path):
    engine = EvidenceEngine(tmp_path)
    records = [{'record_id': str(i), 'kind': kind, 'payload': payload} for i, (kind, payload) in enumerate([
        ('http_response', {'status': 401}), ('http_response', {'status': 422}),
        ('console_error', {'message': 'log'}), ('request_failed', {'message': 'net::ERR_ABORTED'})])]
    assert engine.build_technical(RuntimeObservation(records=records)) == []
