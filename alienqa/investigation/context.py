"""组装 InvestigatorContext（专家可看源码/DOM/技术信号）。"""
from alienqa.i18n import t as tr

import json
from pathlib import Path
from ..driver.runtime import clean_message

from ..context.models import InvestigatorContext
from .retriever import retrieve_source


def build_investigator_context(project, issue, evidences, driver=None) -> InvestigatorContext:
    member_ids = set(getattr(issue, "evidence_ids", []) or [])
    evidences = [ev for ev in (evidences or []) if ev.id in member_ids]
    ctx = InvestigatorContext()
    if project is not None:
        ctx.source = retrieve_source(project, issue, evidences)
    ctx.input_status = {
        "source": {"status": "bounded_snippets" if ctx.source else "unavailable",
                   "limit": tr("所选应用文件片段；不含 source map、组件树或服务端追踪")},
        "missing_members": sorted(member_ids - {ev.id for ev in evidences}),
        "snapshots": [],
        "screenshots": tr("仅提供保存路径与缺失状态；本调查文本通道不读取图片像素"),
    }
    for ev in evidences:
        artifacts = ev.artifacts or {}
        snapshot_status = {"evidence_id": ev.id, "kind": artifacts.get("snapshot_kind", "legacy_unknown")}
        for name in ("dom_before", "dom_after", "before", "after", "technical"):
            path = artifacts.get(name)
            snapshot_status[name] = "saved" if path and Path(path).is_file() else "missing"
        ctx.input_status["snapshots"].append(snapshot_status)
        ctx.evidence_facts.append({"evidence_id": ev.id, "finding_kind": ev.finding_kind,
                                  "step_id": ev.step_id, "action_id": ev.action_id,
                                  "source_record_ids": ev.source_record_ids, "expectation_id": ev.expectation_id,
                                  "expectation_basis": ev.expectation_basis,
                                  "source_signals": (ev.replay or {}).get("source_signals", []),
                                  "target_window": (ev.replay or {}).get("target_window", {}),
                                  "attempts": [{key: attempt.get(key) for key in ("step_id", "action_id", "status", "emitted")}
                                               for attempt in (ev.replay or {}).get("attempts", [])],
                                  "observation_window": (ev.replay or {}).get("observation_window", {}),
                                  "saved_images": {key: artifacts.get(key) for key in ("before", "after")}})
    ctx.dom = _saved_dom(evidences)
    ctx.stack_trace = _stack_trace(evidences)
    ctx.console = _signals(evidences, "console")
    ctx.network = _signals(evidences, "network")
    summary = [tr("问题 {id}：{title}", id=getattr(issue, "id", ""), title=getattr(issue, "title", ""))]
    for ev in evidences:
        summary.append(tr("证据 {id}\n预期：{expectation}\n实际：{observation}\n触发动作：{action}", id=ev.id, expectation=ev.expectation, observation=ev.observation_summary, action=_describe(ev.action)))
    ctx.action_trace = "\n\n".join(summary) + "\n\n" + _action_trace(evidences)
    return ctx


def _saved_dom(evidences) -> str:
    """Use the issue's action-time snapshot; the live browser may be elsewhere."""
    blocks = []
    remaining = 5000
    for ev in evidences:
        for name in ("dom_before", "dom_after"):
            path = (ev.artifacts or {}).get(name)
            if not path or remaining <= 0:
                continue
            try:
                with Path(path).open(encoding="utf-8") as stream:
                    content = stream.read(remaining + 1)
                snapshot = content[:remaining]
            except (OSError, UnicodeError):
                continue
            if snapshot:
                blocks.append(f"{ev.id} {name} ({(ev.artifacts or {}).get('snapshot_kind', 'legacy_unknown')})\n{snapshot}" +
                              (tr("\n[截断：保存快照输入共限 5000 字符]") if len(content) > remaining else ""))
                remaining -= len(snapshot)
    return "\n\n".join(blocks)


def _signals(evidences, key) -> str:
    out = []
    for ev in evidences or []:
        replay = getattr(ev, "replay", None) or {}
        if "source_signals" in replay:
            kinds = {"console": {"console_error", "page_error"}, "network": {"request_failed", "http_response"}}[key]
            out.extend(str(record.get("payload")) for record in replay["source_signals"] if record.get("kind") in kinds)
            continue
        for s in replay.get(key) or []:
            out.append(str(s))
    return "; ".join(out[:20])


def _stack_trace(evidences) -> str:
    for ev in evidences or []:
        if "source_signals" in (ev.replay or {}):
            signals = [record.get("payload", {}).get("message", "") for record in ev.replay["source_signals"]
                       if record.get("kind") == "page_error"]
            if signals:
                return "; ".join(signals[:5])
            continue
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
    return clean_message(f"{t} {label}".strip()) + (tr(" 输入值保留在本机回放包") if action.get("text") else "")
