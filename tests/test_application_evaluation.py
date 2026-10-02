"""Application suite contracts: no external downloads or real model calls."""
import json

import pytest


def application(case_id="notes", **fields):
    return {"id": case_id, "entry_url": "http://127.0.0.1:5231/", "version": "upstream-commit",
            "reset": "Fresh isolated account; empty workspace", "mode": "autonomous", "max_actions": 3, **fields}


def manifest(tmp_path, cases):
    path = tmp_path / "applications.json"
    path.write_text(json.dumps({"schema_version": 1, "version": "application-suite-test", "cases": cases}))
    return path


@pytest.mark.parametrize("fields", [{"version": ""}, {"reset": ""}, {"entry_url": "file:///tmp/app"},
                                   {"mode": "scripted"}, {"max_actions": True}, {"max_actions": 0}])
def test_application_manifest_rejects_unreproducible_runs(tmp_path, fields):
    from alienqa.evaluation import load_application_manifest
    with pytest.raises(ValueError):
        load_application_manifest(manifest(tmp_path, [application(**fields)]))


def test_application_manifest_checks_ids_and_resolves_per_case_sessions(tmp_path):
    from alienqa.evaluation import load_application_manifest
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"cookies": [], "origins": []}))
    loaded = load_application_manifest(manifest(tmp_path, [application(storage_state="session.json")]))
    assert loaded["cases"][0]["storage_state"] == str(session.resolve())
    with pytest.raises(ValueError):
        load_application_manifest(manifest(tmp_path, [application(), application()]))


def test_suite_shares_budget_keeps_unstarted_cases_and_excludes_setup_from_model(tmp_path, monkeypatch):
    import alienqa.evaluation as evaluation
    from alienqa.pipeline import PipelineResult
    from types import SimpleNamespace
    captured = []

    class Pipeline:
        def __init__(self, *args, **kwargs):
            self.client = SimpleNamespace()
            self.directory = kwargs["artifacts_dir"]

        def collect(self, project):
            captured.append(project)
            self.client.before_request("fake/model")
            result = PipelineResult()
            result.save(self.directory)
            return result

    monkeypatch.setattr(evaluation, "AlienQAPipeline", Pipeline)
    monkeypatch.setattr(evaluation, "_serve", lambda *a: pytest.fail("Application-only suite starts no control server"))
    cases = [application("notes", reset="Private setup instruction must stay outside model"),
             application("convert", mode="directed", entry_url="http://127.0.0.1:5051/json-to-yaml")]
    source = manifest(tmp_path, cases)
    output = tmp_path / "results"
    assert evaluation.main(["--applications-manifest", str(source), "--max-calls", "1",
                            "--inference-kind", "substitute", "--output", str(output)]) == 2
    saved = json.loads((output / "evaluation.json").read_text())
    assert saved["invocations_used"] == 1
    assert saved["runs"][1]["status"] == "not_started"
    assert saved["summary"]["planned_runs"] == 2
    assert saved["summary"]["exploration_modes"] == {"autonomous": 1, "directed": 1}
    assert captured[0].visible_files == [] and captured[0].storage_state == ""
    assert "Private setup" not in repr(captured[0])
    frozen = json.loads((output / "manifest.json").read_text())
    assert frozen["judge_prompt_version"] == "judgment-v3"
    assert frozen["cases"][0]["reset"] == cases[0]["reset"]


def test_suite_rejects_mixed_control_and_application_sources(tmp_path):
    import alienqa.evaluation as evaluation
    source = manifest(tmp_path, [application()])
    with pytest.raises(SystemExit):
        evaluation.main(["--applications-manifest", str(source), "--real-app", "http://localhost:1",
                         "--max-calls", "1", "--output", str(tmp_path / "out")])
