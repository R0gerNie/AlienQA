"""Mechanical candidate/report reconciliation, never semantic approval."""
from scripts.summarize_application_suite import audit_run


def test_audit_preserves_union_sources_and_flags_missing_delivery(tmp_path):
    import json
    step = {"step_id": "ST-1", "expectations": [{"id": "EX-1"}],
            "expectation_generation": {"samples": [{"sample_index": 1, "parsed": [{"text": "one"}]},
                {"sample_index": 2, "parsed": [{"text": "two"}]}],
                "groups": [{"expectation_id": "EX-1", "members": [{"sample_index": 1, "row_index": 1},
                    {"sample_index": 2, "row_index": 1}]}]},
            "judgment_outputs": [{"status": "mismatch", "raw": json.dumps({"status": "mismatch",
                "mismatches": [{"expectation_id": "EX-1", "expectation": "one", "observation": "none",
                    "level": "low", "reasoning": "subjective concern"}]})}]}
    evidence = {"id": "EV-1", "step_id": "ST-1", "expectation_id": "EX-1", "finding_kind": "cognitive_mismatch"}
    (tmp_path / "scan.json").write_text(json.dumps({"steps": [step], "evidences": [evidence]}))
    (tmp_path / "analysis.html").write_text("<section>EV-1</section>")
    result = audit_run(tmp_path)
    assert result["source_candidates"] == result["preserved_source_members"] == 2
    assert result["missing_source_members"] == result["mismatches_without_evidence"] == []
    assert result["evidences_missing_from_report"] == []
    (tmp_path / "analysis.html").write_text("<h1>empty</h1>")
    assert audit_run(tmp_path)["evidences_missing_from_report"] == ["EV-1"]


def test_accounting_includes_failed_attempts_and_marks_running_checkpoint(tmp_path, monkeypatch):
    import json
    from scripts import summarize_application_suite as summary
    run = tmp_path / "run-1"
    run.mkdir()
    (run / "scan.json").write_text(json.dumps({"run_id": "run-1", "steps": [], "evidences": []}))
    (tmp_path / "evaluation.json").write_text(json.dumps({"invocations_used": 2, "runs": [
        {"id": "run-1", "case_id": "notes", "mode": "autonomous", "status": "running"}]}))
    monkeypatch.setattr(summary, "load_summary", lambda *args: {"attempts": 2,
        "counts": {"succeeded": 1, "failed": 1}, "tokens": {"prompt_tokens": {"known": 20},
        "completion_tokens": {"known": 3}}, "unknown_cost_attempts": 2, "by_role": {"expectation": {"attempts": 2}}})
    result = summary.summarize(tmp_path)
    assert result["invocations_match_attempts"] is True and result["metered_attempts"] == 2
    assert result["attempt_statuses"]["failed"] == 1 and result["unknown_cost_attempts"] == 2
    assert result["human_review_required"] is False
    assert result["accounting_complete"] is False
