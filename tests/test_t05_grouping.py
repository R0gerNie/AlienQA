from copy import deepcopy

import pytest

from alienqa.dedup import Deduplicator
from alienqa.evidence import Evidence


def evidence(eid, kind="technical_anomaly", selector="#save", basis=None):
    return Evidence(id=eid, finding_kind=kind, classification="technical_bug",
                    action={"type": "click", "target": {"selector": selector}},
                    expectation="应当反馈成功", expectation_basis=basis,
                    observation_summary="保存未成功", replay={"url": "http://x",
                    "source_signals": [{"kind": "page_error", "payload": {"message": "TypeError: save failed"}}]})


@pytest.mark.parametrize("change", ["action", "basis", "expectation", "source"])
def test_distinct_modern_findings_do_not_soft_merge(change):
    a = evidence("EV-1", kind="cognitive_mismatch" if change in {"basis", "expectation"} else "technical_anomaly")
    b = deepcopy(a)
    b.id = "EV-2"
    if change == "action":
        b.action["target"]["selector"] = "#refund"
    elif change == "basis":
        b.expectation_basis = {"visible": "退款"}
    elif change == "expectation":
        b.expectation += "并且关闭弹窗"
    else:
        b.replay["source_signals"][0]["payload"]["message"] += " in different handler"
    before = [deepcopy(a.to_dict()), deepcopy(b.to_dict())]
    assert len(Deduplicator().cluster([a, b])) == 2
    for ev, saved in zip([a, b], before):
        actual = ev.to_dict()
        actual.pop("issue_id")
        saved.pop("issue_id")
        assert actual == saved


def test_duplicate_facts_group_but_cross_kind_members_survive():
    a, b, c = evidence("EV-1"), evidence("EV-2"), evidence("EV-3", kind="cognitive_mismatch")
    issues = Deduplicator().cluster([a, b, c])
    assert sorted(len(i.evidence_ids) for i in issues) == [1, 2]
    assert all(i.to_dict()["grouping_basis"] for i in issues)


def test_group_ids_stable_when_input_reordered_or_extended():
    a, b = evidence("EV-1"), evidence("EV-2", selector="#refund")
    dedup = Deduplicator()
    dedup.cluster([a, b])
    ids = {a.id: a.issue_id, b.id: b.issue_id}
    dedup.cluster([evidence("EV-0", selector="#new"), b, a])
    assert ids == {a.id: a.issue_id, b.id: b.issue_id}
