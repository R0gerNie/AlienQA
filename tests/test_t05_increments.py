"""Optional increments share report lock and never repair the original scan status."""
import importlib
from copy import deepcopy

import pytest

from alienqa.evidence import Evidence
from alienqa.investigation import Investigation
from alienqa.persistence import atomic_write_json
from test_ui_app import _make_app
from alienqa.ui.runs import RunManager


def test_replay_rejects_live_snapshot(tmp_path):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("test")
    runs.save_results(rec.id, [Evidence(id="EV-1")], [])
    response = app.test_client().post(f"/api/run/{rec.id}/replay/EV-1")
    assert response.status_code == 409
    assert "结束" in response.get_json()["error"]


@pytest.mark.parametrize("failure", ["cancelled", "timeout"])
def test_parent_preserves_last_progress_on_stop(tmp_path, failure):
    module = importlib.import_module("alienqa.ui.app")
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("test")
    runs.finish(rec.id, status="partial", error="original incomplete")
    runs.save_replay_result(rec.id, "EV-1", {"status": "running"})
    progress = {"evidence_id": "EV-1", "status": "running", "phase": "target", "interrupted_step_id": "ST-3",
                "preconditions": {"saved_session": "saved"}, "executed_steps": [{"step_id": "ST-2"}]}
    atomic_write_json(rec.dir / "replay_progress/EV-1.json", progress)
    module._complete_replay(app, rec.id, "EV-1", failure)
    result = runs.load_replay_results(rec.id)["EV-1"]
    assert result["status"] == "inconclusive" and result["termination"] == failure
    assert result["interrupted_step_id"] == "ST-3" and result["executed_steps"] == progress["executed_steps"]
    assert runs.get(rec.id).status == "partial"


def test_investigation_increment_invalidates_both_reports_and_keeps_decisions(tmp_path):
    runs = RunManager(tmp_path)
    rec = runs.create("test")
    runs.save_results(rec.id, [Evidence(id="EV-1", issue_id="I")], [])
    runs.finish(rec.id, status="partial")
    before = deepcopy(runs.load_evidences(rec.id)[0].to_dict())
    for name in ("report.html", "analysis.html"):
        (rec.dir / name).write_text("stale")
    runs.save_investigation_result(rec.id, Investigation(issue_id="I", evidence_ids=["EV-1"],
                                                       root_cause_hypothesis="可能未绑定"))
    assert runs.load_investigations(rec.id)[0].root_cause_hypothesis == "可能未绑定"
    assert all(not (rec.dir / name).exists() for name in ("report.html", "analysis.html"))
    assert runs.load_evidences(rec.id)[0].to_dict() == before
    assert runs.get(rec.id).status == "partial"
