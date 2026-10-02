"""Issue-local saved facts; bounded source and explicit hypotheses."""
from types import SimpleNamespace

from alienqa.dedup import Issue
from alienqa.evidence import Evidence
from alienqa.investigation import InvestigationAgent
from alienqa.investigation.context import build_investigator_context
from alienqa.investigation.retriever import retrieve_source


def test_context_has_only_members_and_explicit_missing_inputs(tmp_path):
    snapshot = tmp_path / "visible.txt"
    snapshot.write_text("saved visible text")
    member = Evidence(id="EV-1", finding_kind="technical_anomaly", step_id="ST-2",
                      source_record_ids=["RUN:R-2"], replay={"source_signals": [
                          {"kind": "page_error", "payload": {"message": "TypeError: member only"}}]},
                      artifacts={"dom_after": str(snapshot), "snapshot_kind": "visible_text"})
    other = Evidence(id="EV-2", expectation="UNRELATED", replay={"console": ["UNRELATED"]})
    ctx = build_investigator_context(None, Issue(id="I", evidence_ids=["EV-1", "EV-missing"]), [member, other])
    text = ctx.to_text()
    assert "UNRELATED" not in text
    assert "RUN:R-2" in text and "ST-2" in text and "technical_anomaly" in text
    assert "visible_text" in text and "EV-missing" in text
    assert ctx.input_status["source"]["status"] == "unavailable"
    assert "假设" in text


def test_source_is_bounded_to_selected_root_with_limits(tmp_path):
    root = tmp_path / "selected"
    root.mkdir()
    source = root / "Save.jsx"
    source.write_text("x" * 700)
    outside = tmp_path / "Other.jsx"
    outside.write_text("OUTSIDE_SECRET")
    project = SimpleNamespace(root=str(root), visible_files=[
        SimpleNamespace(path="Save.jsx", role="component"),
        SimpleNamespace(path="../Other.jsx", role="component")])
    result = retrieve_source(project, Issue(title=""))
    assert "OUTSIDE_SECRET" not in result
    assert "Save.jsx" in result and "截断" in result


def test_investigation_preserves_local_context_status_not_model_claims(monkeypatch):
    agent = InvestigationAgent(SimpleNamespace())
    monkeypatch.setattr(agent.roles, "investigate", lambda *args, **kwargs:
        '{"root_cause_hypothesis":"可能是事件未绑定", "status":"verified", "input_status":{"source":"complete"}}')
    monkeypatch.setattr(agent.roles, "mark_parse", lambda *args: None)
    issue = Issue(id="I", evidence_ids=["EV-1"])
    result = agent.investigate_issue(None, issue, [Evidence(id="EV-1")])
    assert result.status == "completed"
    assert result.evidence_ids == ["EV-1"]
    assert result.input_status["source"]["status"] == "unavailable"
    assert result.to_dict()["interpretation"] == "hypothesis"


def test_context_failure_is_a_failed_optional_investigation(monkeypatch):
    agent = InvestigationAgent(SimpleNamespace())
    monkeypatch.setattr("alienqa.investigation.agent.build_investigator_context",
                        lambda *args: (_ for _ in ()).throw(OSError("saved input unavailable")))
    result = agent.investigate_issue(None, Issue(id="I"), [])
    assert result.status == "failed" and "saved input unavailable" in result.error


def test_prompt_budget_declares_truncation_and_keeps_boundaries():
    from alienqa.context.models import InvestigatorContext
    ctx = InvestigatorContext(source='x' * 14000, action_trace='TARGET ACTION',
                              input_status={'source': {'status': 'bounded_snippets'}})
    text = ctx.to_text()
    assert len(text) <= 12000
    assert 'TARGET ACTION' in text and '假设' in text and '截断' in text
    assert ctx.input_status['prompt_truncated'] is True
