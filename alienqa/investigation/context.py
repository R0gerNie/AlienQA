"""组装 InvestigatorContext（专家可看源码/DOM/技术信号）。"""
import json
from pathlib import Path

from ..context.models import InvestigatorContext
from .retriever import retrieve_source


def build_investigator_context(project, issue, evidences, driver=None) -> InvestigatorContext:
    ctx = InvestigatorContext()
    if project is not None:
        ctx.source = retrieve_source(project, issue, evidences)
    if driver is not None:
        ctx.dom = _dom_channel(driver, ctx.source, evidences)
    ctx.stack_trace = _stack_trace(evidences)
    ctx.console = _signals(evidences, "console")
    ctx.network = _signals(evidences, "network")
    ctx.action_trace = _action_trace(evidences)
    return ctx


def _dom_channel(driver, source: str, evidences) -> str:
    """11b：黑盒（无源码）时优先取问题动作 selector 附近的 DOM 子树，控制 prompt 长度。"""
    try:
        selector = ""
        if not source:
            selector = _first_action_selector(evidences)
        if selector:
            subtree = driver.dom(selector)
            if subtree:
                return subtree[:5000]
        return (driver.dom() or "")[:5000]
    except Exception:  # noqa: BLE001
        return ""


def _first_action_selector(evidences) -> str:
    for ev in evidences or []:
        action = getattr(ev, "action", None) or {}
        if isinstance(action, dict):
            sel = (action.get("target") or {}).get("selector")
            if sel:
                return str(sel)
    return ""


def _signals(evidences, key) -> str:
    out = []
    for ev in evidences or []:
        replay = getattr(ev, "replay", None) or {}
        for s in replay.get(key) or []:
            out.append(str(s))
    return "; ".join(out[:20])


def _stack_trace(evidences) -> str:
    for ev in evidences or []:
        artifacts = getattr(ev, "artifacts", None) or {}
        path = artifacts.get("technical")
        if not path:
            continue
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            js = data.get("js_exceptions") or []
            if js:
                return "; ".join(str(x) for x in js[:5])
        except Exception:  # noqa: BLE001
            continue
    return ""


def _action_trace(evidences) -> str:
    out = []
    for ev in evidences or []:
        replay = getattr(ev, "replay", None) or {}
        for i, a in enumerate(replay.get("action_sequence") or [], start=1):
            out.append(f"{i}. {_describe(a)}")
    return "\n".join(out[:20])


def _describe(action) -> str:
    if not isinstance(action, dict):
        return str(action)
    t = action.get("type") or ""
    target = action.get("target") or {}
    if isinstance(target, dict):
        label = target.get("text") or target.get("selector") or ""
    else:
        label = str(target)
    return f"{t} {label}".strip()
