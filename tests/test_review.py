"""Human Review + Report 测试：状态机、排序、gate、报告只含采信、Flask 前端（mock LLM）。"""
from types import SimpleNamespace

import pytest

from alienqa.evidence import Evidence, Severity
from alienqa.llm import LLMClient, LLMConfig, RoleConfig
from alienqa.review import Decision, HumanReview, ReportBuilder, ReviewState, create_app


class _FakeLiteLLM:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = []

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        item = self.texts.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=item))],
            model=kwargs["model"],
            usage=None,
        )


@pytest.fixture
def reporter(monkeypatch):
    fake = _FakeLiteLLM([])
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: fake)
    cfg = LLMConfig(roles={"reporter": RoleConfig(model="gpt-4o", temperature=0.2)})
    return ReportBuilder(LLMClient(cfg)), fake


def _ev(ev_id, severity=Severity.MINOR, expectation="", replay=None):
    return Evidence(id=ev_id, severity=severity, expectation=expectation,
                    replay=replay or {"action_sequence": []})


# ---- 状态机 ----

def test_decision_state_machine():
    st = ReviewState()
    assert st.decision("EV-1") == Decision.PENDING
    st.decide("EV-1", Decision.CONFIRMED, "ok")
    assert st.decision("EV-1") == Decision.CONFIRMED
    st.decide("EV-1", Decision.REJECTED)  # 可回退
    assert st.decision("EV-1") == Decision.REJECTED


# ---- 排序 ----

def test_sort_severity_and_alphabetical():
    review = HumanReview()
    evs = [
        _ev("EV-003", Severity.CRITICAL),
        _ev("EV-001", Severity.TRIVIAL),
        _ev("EV-002", Severity.MAJOR),
    ]
    assert [e.id for e in review.sorted_evidences(evs, by="severity")] == ["EV-003", "EV-002", "EV-001"]
    assert [e.id for e in review.sorted_evidences(evs, by="alphabetical")] == ["EV-001", "EV-002", "EV-003"]


def test_accepted_only():
    review = HumanReview()
    evs = [_ev("EV-001"), _ev("EV-002")]
    review.decide("EV-001", Decision.CONFIRMED)
    review.decide("EV-002", Decision.REJECTED)
    assert [e.id for e in review.accepted(evs)] == ["EV-001"]


# ---- 报告 gate 与只含采信 ----

def test_report_only_confirmed(reporter):
    builder, fake = reporter
    fake.texts.append("<h1>报告</h1>")
    evs = [_ev("EV-001", expectation="点保存应有提示"), _ev("EV-002", expectation="点删除应有确认")]
    state = ReviewState()
    state.decide("EV-001", Decision.CONFIRMED)
    state.decide("EV-002", Decision.REJECTED)
    r = builder.build(evs, state)
    assert r.accepted_count == 1
    assert r.total_count == 2
    prompt = fake.calls[0]["messages"][0]["content"]
    assert "EV-001" in prompt
    assert "EV-002" not in prompt


def test_report_is_styled_html_document(reporter):
    """模块 12 的永久报告编排器：产出带样式的完整 HTML 文档。"""
    builder, fake = reporter
    fake.texts.append("<h1>报告</h1><section>内容</section>")
    state = ReviewState()
    state.decide("EV-001", Decision.CONFIRMED)
    r = builder.build([_ev("EV-001", expectation="x")], state)
    assert r.html.startswith("<!doctype html>")
    assert "<style>" in r.html
    assert "<h1>报告</h1>" in r.html


def test_report_blocks_on_by_design(reporter):
    builder, _ = reporter
    state = ReviewState()
    state.decide("EV-001", Decision.BY_DESIGN)
    with pytest.raises(ValueError, match="by-design"):
        builder.build([_ev("EV-001")], state)


def test_report_blocks_on_pending(reporter):
    builder, _ = reporter
    with pytest.raises(ValueError, match="尚未审核"):
        builder.build([_ev("EV-001")], ReviewState())


# ---- Flask 前端 ----

def test_flask_decide_and_report(reporter):
    builder, fake = reporter
    fake.texts.append("<h1>报告</h1>")
    review = HumanReview()
    app = create_app(review, builder)
    app.config["evidences"] = [_ev("EV-001", expectation="点保存应有提示")]
    client = app.test_client()
    # 未审核 → 409
    assert client.get("/report").status_code == 409
    # 采信
    assert client.post("/decide", json={"evidence_id": "EV-001", "decision": "confirmed"}).status_code == 200
    r = client.get("/report")
    assert r.status_code == 200
    assert "报告" in r.get_data(as_text=True)


def test_flask_index_renders_switcher(reporter):
    builder, _ = reporter
    review = HumanReview()
    app = create_app(review, builder)
    app.config["evidences"] = [_ev("EV-001", expectation="点保存应有提示")]
    client = app.test_client()
    html = client.get("/").get_data(as_text=True)
    assert "EV-001" in html
    assert "checkbox" in html


def test_flask_report_persists_to_file(reporter, tmp_path):
    builder, fake = reporter
    fake.texts.append("<h1>报告</h1><section>内容</section>")
    review = HumanReview()
    out = tmp_path / "report.html"
    app = create_app(review, builder, report_path=str(out))
    app.config["evidences"] = [_ev("EV-001", expectation="点保存应有提示")]
    review.decide("EV-001", Decision.CONFIRMED)
    client = app.test_client()
    assert client.get("/report").status_code == 200
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "<h1>报告</h1>" in html


def test_flask_report_includes_investigations(reporter):
    builder, fake = reporter
    fake.texts.append("<h1>报告</h1>")
    review = HumanReview()
    inv = SimpleNamespace(
        issue_id="ISSUE-001",
        root_cause_hypothesis="端口受限导致 net::ERR_UNSAFE_PORT",
        reproduction_steps=["1. 点击 Fetch refused"],
    )
    app = create_app(review, builder, investigations=[inv])
    ev = Evidence(
        id="EV-001",
        issue_id="ISSUE-001",
        expectation="点击应得到反馈",
        replay={"action_sequence": []},
    )
    app.config["evidences"] = [ev]
    review.decide("EV-001", Decision.CONFIRMED)
    client = app.test_client()
    assert client.get("/report").status_code == 200
    prompt = fake.calls[0]["messages"][0]["content"]
    assert "端口受限导致 net::ERR_UNSAFE_PORT" in prompt
