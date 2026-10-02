import json

import pytest

from alienqa.evidence import Evidence
from alienqa.run_writer import RunWriter, StorageError, load_snapshot
from alienqa.ui.runs import RunManager


def test_checkpoint_failure_keeps_previous_authority(tmp_path, monkeypatch):
    writer = RunWriter(tmp_path, "run-1")
    writer.checkpoint(phase="entry", steps=[], evidences=[], diagnostics=[])
    first = load_snapshot(tmp_path)
    import alienqa.run_writer as module
    original = module.atomic_write_json

    def fail_commit(path, payload):
        if path.name == "scan.json":
            raise OSError("disk full")
        original(path, payload)

    monkeypatch.setattr(module, "atomic_write_json", fail_commit)
    with pytest.raises(StorageError, match="disk full"):
        writer.checkpoint(phase="judgment", steps=[{"step_id": "ST-1"}],
                          evidences=[Evidence(id="EV-1")], diagnostics=[])
    assert load_snapshot(tmp_path) == first


def test_checkpoint_read_states_and_raw_reference_validation(tmp_path):
    assert load_snapshot(tmp_path) is None
    writer = RunWriter(tmp_path, "run-1")
    ref = writer.save_raw({"records": [{"record_id": "R-1"}], "window": {}}, phase="entry")
    writer.checkpoint(phase="entry", steps=[], evidences=[], diagnostics=[], raw_refs=[ref])
    assert load_snapshot(tmp_path)["raw_refs"] == [ref]
    (tmp_path / ref["path"]).unlink()
    with pytest.raises(StorageError, match="raw"):
        load_snapshot(tmp_path)
    (tmp_path / "scan.json").write_text("broken")
    with pytest.raises(StorageError) as error:
        load_snapshot(tmp_path)
    assert error.value.status == "corrupt"
    (tmp_path / "scan.json").write_text(json.dumps({"schema_version": 999}))
    with pytest.raises(StorageError) as error:
        load_snapshot(tmp_path)
    assert error.value.status == "unsupported"


def test_history_reads_committed_prefix_and_terminal_append(tmp_path):
    runs = RunManager(tmp_path)
    rec = runs.create("https://app.test", mode="browser")
    writer = RunWriter(rec.dir, rec.id)
    ev = Evidence(id="EV-1", finding_kind="technical_anomaly", run_id=rec.id)
    writer.checkpoint(phase="visual", steps=[{"step_id": "ST-1", "status": "inconclusive",
                                             "cognitive_status": "pending"}],
                      evidences=[ev], diagnostics=[])
    (rec.dir / "evidences.json").write_text("[]")  # stale export is not authoritative
    runs.append_terminal_diagnostic(rec.id, "cancelled", "user stopped")
    assert runs.load_evidences(rec.id)[0].finding_kind == "technical_anomaly"
    saved = runs.load_diagnostics(rec.id)
    assert saved["steps"][0]["cognitive_status"] == "inconclusive"
    assert saved["incomplete"] is True and saved["stop_reason"] == "cancelled"


def test_old_evidence_and_missing_diagnostics_are_not_backfilled(tmp_path):
    runs = RunManager(tmp_path)
    rec = runs.create("old")
    (rec.dir / "evidences.json").write_text('[{"id":"old"}]')
    assert runs.load_evidences(rec.id)[0].finding_kind is None
    assert runs.load_evidences(rec.id)[0].expectation_basis is None
    assert runs.load_diagnostics(rec.id)["data_status"] == "absent"
    assert runs.load_diagnostics(rec.id)["incomplete"] is True


def test_corrupt_snapshot_is_explicit_in_history_and_evidence_read(tmp_path):
    runs = RunManager(tmp_path)
    rec = runs.create("broken")
    (rec.dir / "scan.json").write_text('bad json')
    assert runs.load_diagnostics(rec.id)["data_status"] == "corrupt"
    with pytest.raises(StorageError):
        runs.load_evidences(rec.id)


def test_timeout_preserves_prefix_and_marks_unclosed_phase(tmp_path):
    runs = RunManager(tmp_path)
    rec = runs.create("timeout")
    writer = RunWriter(rec.dir, rec.id)
    writer.checkpoint(phase="judgment", steps=[{"status": "inconclusive", "cognitive_status": "pending",
                                              "phases": {"judgment": "started"}}],
                      evidences=[], diagnostics=[])
    saved = runs.append_terminal_diagnostic(rec.id, "timeout", "worker stopped")
    assert saved["steps"][0]["phases"]["judgment"] == "incomplete"
    assert saved["stop_reason"] == "timeout"


def test_missing_v2_authority_does_not_fall_back_to_exports(tmp_path):
    runs = RunManager(tmp_path)
    rec = runs.create("missing")
    RunWriter(rec.dir, rec.id).checkpoint(phase="terminal", steps=[], evidences=[], diagnostics=[])
    (rec.dir / "scan.json").unlink()
    assert runs.load_diagnostics(rec.id)["data_status"] == "absent"
    assert runs.load_diagnostics(rec.id)["incomplete"] is True
    with pytest.raises(StorageError, match="missing committed"):
        runs.load_evidences(rec.id)


@pytest.mark.parametrize("mutation", ["missing", "text", "basis", "action"])
def test_cognitive_evidence_requires_committed_expectation_lineage(tmp_path, mutation):
    writer = RunWriter(tmp_path, "run")
    basis = {"type": "visible_copy", "reference": "保存"}
    exp = {"id": "EX-ST-00001-001", "text": "保存后有反馈", "expectation_basis": basis,
           "run_id": "run", "step_id": "ST-00001", "action_id": "A-00001"}
    ev = Evidence(id="EV-00001", schema_version=2, finding_kind="cognitive_mismatch",
                  expectation_id=exp["id"], expectation=exp["text"], expectation_basis=basis,
                  run_id="run", step_id="ST-00001", action_id="A-00001")
    writer.checkpoint(phase="terminal", steps=[{"step_id": "ST-00001", "action_id": "A-00001", "expectations": [exp]}],
                      evidences=[ev], diagnostics=[])
    assert load_snapshot(tmp_path)["evidences"][0]["expectation_id"] == exp["id"]
    data = json.loads((tmp_path / "scan.json").read_text())
    if mutation == "missing":
        data["steps"][0]["expectations"] = []
    elif mutation == "text":
        data["evidences"][0]["expectation"] = "伪造预期"
    elif mutation == "basis":
        data["evidences"][0]["expectation_basis"]["reference"] = "伪造依据"
    else:
        data["evidences"][0]["action_id"] = "OTHER"
    (tmp_path / "scan.json").write_text(json.dumps(data))
    with pytest.raises(StorageError, match="expectation"):
        load_snapshot(tmp_path)
