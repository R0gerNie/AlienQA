"""RunManager 历史扫描目录管理测试。"""
from alienqa.ui import RunManager


def test_create_and_finish(tmp_path):
    rm = RunManager(tmp_path / "runs")
    rec = rm.create("d:/project", unit="登录页", entry="index.html")
    assert rec.status == "running"
    assert (rec.dir / "run.json").exists()
    assert rec.project_path == "d:/project"
    assert rec.unit == "登录页"
    assert rec.entry == "index.html"

    rm.finish(rec.id, "done", evidence_count=5, issue_count=2, accepted_count=5)
    got = rm.get(rec.id)
    assert got.status == "done"
    assert got.evidence_count == 5
    assert got.issue_count == 2
    assert got.accepted_count == 5
    assert got.finished_at


def test_list_reverse_chronological_and_unknown(tmp_path):
    rm = RunManager(tmp_path / "runs")
    r1 = rm.create("d:/a")
    r2 = rm.create("d:/b")
    listed = [r.id for r in rm.list()]
    assert listed.index(r2.id) < listed.index(r1.id)  # 新的在前
    # 无 run.json 的目录 → unknown
    stray = tmp_path / "runs" / "stray"
    stray.mkdir(parents=True)
    assert "stray" in [r.id for r in rm.list()]


def test_create_unique_ids(tmp_path):
    rm = RunManager(tmp_path / "runs")
    a = rm.create("d:/x", entry="index.html")
    b = rm.create("d:/x", entry="index.html")
    assert a.id != b.id


def test_run_record_instructions(tmp_path):
    rm = RunManager(tmp_path / "runs")
    rec = rm.create("d:/p", unit="登录表单", instructions="错误密码应有提示")
    assert rec.instructions == "错误密码应有提示"
    assert rm.get(rec.id).instructions == "错误密码应有提示"


def test_save_and_load_scope(tmp_path):
    from types import SimpleNamespace

    rm = RunManager(tmp_path / "runs")
    rec = rm.create("d:/p", unit="登录表单", instructions="错误密码应有提示")
    scope = SimpleNamespace(unit="登录表单", instructions="错误密码应有提示",
                            selectors=["#login"], keywords=["登录"], summary="登录表单")
    rm.save_scope(rec.id, scope)
    loaded = rm.load_scope(rec.id)
    assert loaded["summary"] == "登录表单"
    assert loaded["selectors"] == ["#login"]
    assert loaded["keywords"] == ["登录"]


def test_save_and_load_results_and_review(tmp_path):
    from alienqa.evidence import Evidence, Severity
    from alienqa.investigation import Investigation
    from alienqa.review import Decision

    rm = RunManager(tmp_path / "runs")
    rec = rm.create("d:/p", entry="index.html")
    ev = Evidence(id="EV-001", issue_id="ISSUE-001", expectation="点保存应有提示",
                  severity=Severity.MAJOR, reasoning="r")
    inv = Investigation(issue_id="ISSUE-001", root_cause_hypothesis="端口受限",
                        reproduction_steps=["1. 点击"])
    rm.save_results(rec.id, [ev], [inv])

    evs = rm.load_evidences(rec.id)
    assert evs[0].id == "EV-001"
    assert evs[0].severity == Severity.MAJOR
    assert evs[0].issue_id == "ISSUE-001"
    invs = rm.load_investigations(rec.id)
    assert invs[0].root_cause_hypothesis == "端口受限"

    state = rm.load_review(rec.id)
    state.decide("EV-001", Decision.CONFIRMED)
    rm.save_review(rec.id, state)
    assert rm.load_review(rec.id).decision("EV-001") == Decision.CONFIRMED
