"""Investigation Agent 测试：源码检索、白名单、验收、隔离、重试（mock LLM）。"""
from types import SimpleNamespace

import pytest

from alienqa.context import ExplorerContext, InvestigatorContext
from alienqa.dedup import Issue
from alienqa.evidence import Evidence, Severity
from alienqa.investigation import InvestigationAgent, build_investigator_context, retrieve_source
from alienqa.investigation.models import parse_investigation
from alienqa.llm import LLMClient, LLMConfig, RoleConfig
from alienqa.loader import Project, VisibleFile


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
def agent(monkeypatch):
    fake = _FakeLiteLLM([])
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: fake)
    cfg = LLMConfig(roles={"investigator": RoleConfig(model="gpt-4o", temperature=0.1)})
    return InvestigationAgent(LLMClient(cfg)), fake


def _issue():
    return Issue(id="ISSUE-007", title="退款 Modal 内容为空", evidence_ids=["EV-001"], severity=Severity.MAJOR)


def _evidence(action_seq=None):
    return Evidence(
        id="EV-001",
        expectation="点击申请退款应有内容",
        action={"type": "click", "target": {"text": "申请退款"}},
        replay={
            "url": "http://x/orders",
            "action_sequence": action_seq or [{"type": "click", "target": {"text": "申请退款"}}],
            "console": [],
            "network": [],
        },
    )


# ---- 源码检索 ----

def test_retrieve_source_filters_by_keyword(tmp_path):
    (tmp_path / "components").mkdir()
    (tmp_path / "components" / "RefundModal.tsx").write_text(
        "export function RefundModal() { return <div/> }", encoding="utf-8"
    )
    (tmp_path / "components" / "OrderDetail.tsx").write_text(
        "export function OrderDetail() {}", encoding="utf-8"
    )
    project = Project(root=str(tmp_path), visible_files=[
        VisibleFile(path="components/RefundModal.tsx", role="component"),
        VisibleFile(path="components/OrderDetail.tsx", role="component"),
    ])
    src = retrieve_source(project, _issue(), [_evidence()])
    assert "RefundModal" in src
    assert "OrderDetail" not in src


# ---- 白名单 ----

def test_parse_whitelist_drops_extra_fields():
    inv = parse_investigation(
        '{"root_cause_hypothesis": "h", "reproduction_steps": ["1"],'
        ' "technical_evidence": {}, "affected_components": ["A"], "unwanted": 123}',
        "ISSUE-001",
    )
    assert inv.root_cause_hypothesis == "h"
    assert not hasattr(inv, "unwanted")


# ---- 验收：空 Modal 指向正确组件 + 可执行复现 ----

def test_investigate_end_to_end(agent, tmp_path):
    inv_agent, fake = agent
    (tmp_path / "components").mkdir()
    (tmp_path / "components" / "RefundModal.tsx").write_text(
        "export function RefundModal({children}) { return <div>{children}</div> }", encoding="utf-8"
    )
    project = Project(root=str(tmp_path), visible_files=[
        VisibleFile(path="components/RefundModal.tsx", role="component")
    ])
    fake.texts.append(
        '{"root_cause_hypothesis": "RefundModal 在退款状态下未渲染 children，导致空 Modal",'
        ' "reproduction_steps": ["1. 登录 -> 订单列表", "2. 对已退款订单点击申请退款"],'
        ' "technical_evidence": {"component": "RefundModal.tsx"},'
        ' "affected_components": ["RefundModal", "OrderDetail"]}'
    )
    inv = inv_agent.investigate_issue(project, _issue(), [_evidence()])
    assert inv.issue_id == "ISSUE-007"
    assert "RefundModal" in inv.root_cause_hypothesis
    assert len(inv.reproduction_steps) >= 1
    assert "RefundModal" in inv.affected_components
    # 专家上下文确实包含检索到的源码
    prompt = fake.calls[0]["messages"][0]["content"]
    assert "RefundModal.tsx" in prompt


def test_action_trace_in_context():
    ctx = build_investigator_context(None, _issue(), [_evidence()])
    assert "申请退款" in ctx.action_trace
    assert "申请退款" in ctx.to_text()


def test_investigate_retries_on_bad_json(agent):
    inv_agent, fake = agent
    fake.texts.extend([
        "not json",
        '{"root_cause_hypothesis": "x", "reproduction_steps": ["1. a"],'
        ' "technical_evidence": {}, "affected_components": ["A"]}',
    ])
    inv = inv_agent.investigate(_issue(), InvestigatorContext(source="s"))
    assert inv.root_cause_hypothesis == "x"
    assert len(fake.calls) == 2
    assert "不是合法 JSON" in fake.calls[1]["messages"][0]["content"]


def test_investigator_isolated_from_explorer():
    inv = InvestigatorContext(source="RefundModal.tsx", dom="<div/>")
    assert inv.source == "RefundModal.tsx"
    assert not hasattr(ExplorerContext(), "source")
