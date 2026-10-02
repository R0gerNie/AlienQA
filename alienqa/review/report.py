"""All-findings analysis or confirmed report; recorded evidence is deterministic."""
import base64
import json
import mimetypes
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from ..llm import LLMClient, LlmRoles
from .models import Decision, Report, ReviewState
from .service import DECISION_LABELS, report_mode
from ..cognitive_diagnostics import generation_view
from ..llm.metering import MeteringSink, load_summary
from contextlib import nullcontext

# 报告基础样式：LLM 只产出 body 片段，这里包装成带 CSS 的可读 HTML 文档。
_REPORT_STYLE = """
<style>
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
         max-width: 920px; margin: 2rem auto; padding: 0 1rem;
         color: #1f2328; line-height: 1.6; }
  h1 { border-bottom: 2px solid #1f2328; padding-bottom: .4em; }
  h2 { margin-top: 1.6em; border-left: 4px solid #0969da; padding-left: .6em; }
  section { border: 1px solid #d0d7de; border-radius: 8px;
            padding: 1em 1.2em; margin: 1.2em 0; background: #fff; }
  table { border-collapse: collapse; width: 100%; margin: .5em 0; }
  th, td { border: 1px solid #d0d7de; padding: .45em .7em; text-align: left; vertical-align: top; }
  th { background: #f6f8fa; white-space: nowrap; }
  code { background: #f6f8fa; padding: .12em .35em; border-radius: 4px;
         font-family: ui-monospace, SFMono-Regular, monospace; font-size: .9em; }
  ol, ul { margin: .4em 0; padding-left: 1.7em; }
  hr { border: none; border-top: 1px dashed #d0d7de; margin: 1.5em 0; }
  small { color: #57606a; }
  img { display: block; max-width: 100%; border: 1px solid #d0d7de; }
  pre { white-space: pre-wrap; overflow-wrap: anywhere; }
  .warning { background: #fff8c5; border: 1px solid #d4a72c; padding: 1rem; }
</style>
"""


def render_report_html(fragment: str, mode="confirmed") -> str:
    """把 LLM 产出的 body 片段包装成带样式的完整 HTML 文档。"""
    return (
        "<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
        f"<title>AlienQA {'QA 与用户认知分析' if mode == 'analysis' else '疑似问题报告'}</title>"
        f"{_REPORT_STYLE}</head><body>"
        f"{fragment}</body></html>"
    )


class ReportBuilder:
    def __init__(self, client: LLMClient):
        self.client = client
        self.roles = LlmRoles(client)

    def build(self, evidences, state: ReviewState, investigations=None, diagnostics=None,
              *, mode="confirmed", scan_context=None) -> Report:
        report_mode(mode)
        if mode == "confirmed":
            self._validate(evidences, state)
        accepted = [e for e in evidences if state.decision(e.id) == Decision.CONFIRMED]
        displayed = list(evidences) if mode == "analysis" else accepted
        context = scan_context or {}
        if context.get("run_dir") and context.get("run_id") and isinstance(self.client, LLMClient):
            self.client.sink = MeteringSink(context["run_dir"], context["run_id"])
        inv_map = {inv.issue_id: inv for inv in (investigations or []) if getattr(inv, "issue_id", "")}
        records = [_evidence_dict(e, inv_map.get(e.issue_id), context.get("run_dir"), state, context)
                   for e in displayed]
        fragment = _render_recorded_evidence(displayed, inv_map, len(evidences), diagnostics, state, mode, context, len(accepted))
        if displayed:
            try:
                scope = self.client.call_scope(phase="reporter", step_id=None, action_id=None,
                                               input_ref="evidences.json+review.json") if isinstance(self.client, LLMClient) else nullcontext()
                with scope:
                    summary = self.roles.compose_report(json.dumps(records, ensure_ascii=False, indent=2), mode=mode)
            except Exception:  # noqa: BLE001 deterministic records survive optional model failure
                summary = ""
            if summary:
                fragment += "<details><summary>模型编排补充（原始证据以上方记录为准）</summary>" + _sanitize_summary(summary) + "</details>"
        if context.get("run_dir") and context.get("run_id"):
            usage = load_summary(context["run_dir"], context["run_id"])
            fragment += "<h2>LLM 调用与用量</h2><p>已知小计与未知项分别列示，缺少费用不等于免费。</p>"
            if not usage.get("scan_accounting_recorded"):
                fragment += "<p>扫描调用账目未记录；本节只包含后续实际记录的调用，不能当作整次扫描的总成本。</p>"
            fragment += _pre(usage)
        return Report(html=render_report_html(fragment, mode), accepted_count=len(accepted),
                      total_count=len(evidences), mode=mode, displayed_count=len(displayed))

    def _validate(self, evidences, state: ReviewState) -> None:
        for e in evidences:
            d = state.decision(e.id)
            if d in (Decision.BY_DESIGN, Decision.SKIPPED):
                raise ValueError(f"证据 {e.id} 仍处于 {d.value} 状态，报告生成前必须清空 by-design/skipped")
            if d is Decision.PENDING:
                raise ValueError(f"证据 {e.id} 尚未审核，不能生成报告")


def _public_data(value):
    """Do not serialize local session packages, even when nested in artifacts."""
    if isinstance(value, dict):
        return {key: _public_data(item) for key, item in value.items()
                if key.lower() not in {"cookies", "storage_state", "origins"}}
    if isinstance(value, list):
        return [_public_data(item) for item in value]
    return value


def _artifact_path(path, run_dir=None):
    path = Path(path)
    return Path(run_dir) / path if run_dir and not path.is_absolute() else path


def _evidence_dict(e, investigation=None, run_dir=None, state=None, context=None) -> dict:
    members = getattr(investigation, "evidence_ids", []) or []
    if members and e.id not in members:
        investigation = None
    context = context or {}
    step = next((s for s in context.get("steps", []) if e.step_id and s.get("step_id") == e.step_id), {})
    return _public_data({
        "id": e.id, "severity": e.severity.value, "finding_kind": e.finding_kind,
        "expectation": e.expectation, "expectation_basis": e.expectation_basis,
        "observation": e.observation_summary, "reasoning": e.reasoning,
        "classification": e.classification, "action": e.action,
        "source_record_ids": e.source_record_ids, "expectation_id": e.expectation_id,
        "run_id": e.run_id, "step_id": e.step_id, "action_id": e.action_id,
        "decision": state.decision(e.id).value if state else "pending", "note": state.note(e.id) if state else "",
        "reproduction": _repro(e),
        "root_cause": getattr(investigation, "root_cause_hypothesis", ""),
        "environment": {key: (e.replay or {}).get(key) for key in ("url", "final_url", "browser", "viewport")},
        "visible_before": (step.get("input") or {}).get("visible_text"),
        "visible_after": step.get("visible_result"),
        "technical_signals": _technical(e, run_dir),
        "replay_result": context.get("replay_results", {}).get(e.id),
        "investigation": {
            "status": getattr(investigation, "status", "completed"), "error": getattr(investigation, "error", ""),
            "reproduction_suggestion": list(getattr(investigation, "reproduction_steps", []) or []),
            "technical_evidence": getattr(investigation, "technical_evidence", {}) or {},
            "input_status": getattr(investigation, "input_status", {}) or {},
            "interpretation": "hypothesis",
        } if investigation else {},
    })


def _repro(e) -> list:
    seq = list((e.replay or {}).get("action_sequence") or [])
    if (e.replay or {}).get("target_action"):
        seq.append(e.replay["target_action"])
    out = [f"打开初始页面 {(e.replay or {}).get('url')}"] if (e.replay or {}).get("url") else []
    for a in seq:
        if isinstance(a, dict):
            target = a.get("target") or {}
            label = (target.get("text") or target.get("selector") or "") if isinstance(target, dict) else str(target)
            desc = f"{a.get('type', '')} {label}".strip()
            if a.get("text"):
                desc += f" 输入：{a['text']}"
            out.append(desc)
        else:
            out.append(str(a))
    return [x for x in out if x]


def _technical(e, run_dir=None) -> dict:
    signals = {key: (e.replay or {}).get(key) or []
               for key in ("console", "network", "js_exceptions", "http_status")}
    path = (e.artifacts or {}).get("technical")
    if path:
        try:
            signals["recorded_runtime"] = json.loads(_artifact_path(path, run_dir).read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            signals["artifact_error"] = f"技术记录不可读取：{exc}"
    else:
        signals["artifact_status"] = "技术记录文件未记录"
    return _public_data(signals)


def _render_recorded_evidence(displayed, inv_map, total, diagnostics, state, mode, context, accepted_count):
    title = "QA 与用户认知分析" if mode == "analysis" else "疑似问题报告"
    parts = [f"<h1>AlienQA {title}</h1>", f"<p>人工采信 {accepted_count} 条 / 收集 {total} 条 / 本报告展示 {len(displayed)} 条。</p>"]
    metadata = {key: context[key] for key in ("run_id", "status", "input_type", "base_url", "started_at", "finished_at",
                "checkpoint_seq", "phase", "stop_reason", "incomplete", "scope", "budget", "data_status", "source_context") if key in context}
    if metadata:
        metadata.setdefault("budget", "未记录运行预算")
    parts.append("<h2>扫描范围与完整性</h2>" + (_pre(metadata) if metadata else "<p>旧记录：扫描范围及完整性未记录。</p>"))
    if diagnostics or context.get("incomplete") or context.get("status") in {"partial", "error", "timeout", "cancelled"}:
        parts.append('<div class="warning"><strong>扫描不完整</strong>：执行或判断有失败、缺失或提前终止，不能将未发现问题视为通过。' + _pre(diagnostics or []) + "</div>")
    if not total:
        parts.append("<p>未记录发现；此结果不代表已覆盖所有功能或证明产品无问题。</p>")
    elif not displayed:
        parts.append("<p>本次没有人工采信的证据；此结果不代表已覆盖所有功能或证明产品无问题。</p>")
    if context.get("steps"):
        fields = ("step_id", "action_id", "action", "status", "execution_status", "cognitive_status", "error", "execution", "interaction_coverage", "trajectory")
        parts.append("<h3>探索步骤</h3>" + _pre([{k: s[k] for k in fields if k in s} for s in context["steps"]]))
        parts.append("<h3>认知采样与未决要求</h3>")
        for step in context["steps"]:
            view = generation_view(step)
            parts.append("<h4>" + escape(str(step.get("step_id", "未记录步骤"))) + "</h4>")
            coverage = "未记录" if view["coverage"] == "unrecorded" else view["coverage"]
            local = "未记录" if view["local_judgment_status"] == "unrecorded" else view["local_judgment_status"]
            parts.append("<p>检查覆盖：" + escape(coverage) + "；局部判定：" + escape(local) + "</p>")
            if view["coverage"] == "partial":
                parts.append('<p class="warning">部分要求仍未决，局部判定不代表完整通过。</p>')
            if view["unverifiable_expectation_ids"]:
                parts.append("<p>另有无法判断的要求；已产生的落差仍保留。</p>" + _pre(view["unverifiable_expectation_ids"]))
            if view["relationship_warnings"]:
                parts.append("<p>采样关系备注：全部候选仍交付检查。</p>" + _pre(view["relationship_warnings"]))
            if view["sampling"]:
                parts.append("<p>采样完成情况</p>" + _pre(view["sampling"]))
            else:
                parts.append("<p>旧记录：采样完成情况未记录。</p>")
            parts.append("<p>事前采样要求与未决原因</p>" + _pre(view))
    for ev in displayed:
        inv = inv_map.get(ev.issue_id)
        members = getattr(inv, "evidence_ids", []) or []
        if members and ev.id not in members:
            inv = None
        record = _evidence_dict(ev, inv, context.get("run_dir"), state, context)
        parts.append(f'<section id="{escape(ev.id, quote=True)}"><h2>{escape(ev.id)} · {escape(ev.severity.value)}</h2>')
        complete = "必要记录已声明（以下逐项核对文件可读性）" if ev.is_complete() else "记录不完整或旧记录缺失"
        parts.append("<table>" + "".join(f"<tr><th>{label}</th><td>{escape(str(value or '未记录'))}</td></tr>"
            for label, value in (("发现来源", ev.finding_kind), ("记录完整性", complete), ("采集时间", ev.timestamp),
                ("问题组", ev.issue_id), ("步骤 / 动作", f"{ev.step_id or '未记录'} / {ev.action_id or '未记录'}"),
                ("动作前状态", ev.before_state_id), ("动作后状态", ev.after_state_id))) + "</table>")
        parts.append("<h3>记录环境与原始动作</h3>" + _pre(record["environment"]) + _pre(record["action"]))
        parts.append("<h3>原始复现步骤</h3>" + (_list(record["reproduction"], ordered=True) if record["reproduction"] else "<p>未记录动作序列。</p>"))
        if (ev.replay or {}).get("storage_state") or (ev.replay or {}).get("cookies"):
            parts.append("<p>扫描使用了本机保存的会话状态；独立报告不包含登录凭据。请用本地回放包还原同一会话。</p>")
        parts.append("<h3>采集可见文字（动作前 / 后）</h3>" + _pre({"before": record["visible_before"] if record["visible_before"] is not None else "未记录",
                                                                                "after": record["visible_after"] if record["visible_after"] is not None else "未记录"}))
        parts.append("<h3>记录技术信号及来源 ID</h3>" + _pre(record["source_record_ids"]) + _pre(record["technical_signals"]))
        parts.append("<h3>动作前后截图</h3>")
        for name, label in (("before", "动作前"), ("after", "动作后")):
            parts.append(_image((ev.artifacts or {}).get(name), label, context.get("run_dir")))
        dom = (ev.artifacts or {}).get("dom")
        if dom:
            try:
                text = _artifact_path(dom, context.get("run_dir")).read_text(encoding="utf-8")
                parts.append("<details><summary>采集 DOM（文本）</summary><pre>" + escape(text) + "</pre></details>")
            except (OSError, UnicodeError):
                parts.append("<p>DOM 记录不可读取。</p>")
        parts.append("<h3>事前预期</h3><p>" + escape(ev.expectation or ("技术候选：认知预期不适用" if ev.finding_kind == "technical_anomaly" else "未记录")) + "</p>")
        parts.append("<h3>事前依据</h3>" + (_pre(record["expectation_basis"]) if record["expectation_basis"] is not None else
                      "<p>" + ("技术候选：认知依据不适用（null）" if ev.finding_kind == "technical_anomaly" else "旧记录：未记录依据") + "</p>"))
        parts.append("<h3>观察摘要与推理</h3><p>" + ("技术候选摘要（由采集信号生成）" if ev.finding_kind == "technical_anomaly" else "模型观察摘要（解释）") + "</p>" + _pre({"summary": ev.observation_summary, "reasoning": ev.reasoning, "classification": ev.classification}))
        parts.append("<h3>根因假设</h3><p>" + escape(record["root_cause"] or "尚未建立根因假设") + "</p>")
        if inv:
            parts.append("<p>调查状态：" + escape(record["investigation"]["status"]) + "</p>")
            if getattr(inv, "status", "completed") == "failed":
                parts.append("<p>专家调查失败：" + escape(getattr(inv, "error", "")) + "</p>")
            if record["investigation"]["reproduction_suggestion"]:
                parts.append("<h3>调查建议步骤（未经重放验证）</h3>" + _list(record["investigation"]["reproduction_suggestion"], ordered=True))
            parts.append("<h3>调查技术依据</h3>" + _pre(record["investigation"]["technical_evidence"]))
            parts.append("<h3>调查输入范围与限制</h3>" + _pre(record["investigation"]["input_status"]))
        else:
            parts.append("<p>调查未记录。</p>")
        parts.append("<h3>回放验证</h3>" + (_pre(record["replay_result"]) if record["replay_result"] else "<p>尚未验证。</p>"))
        decision = record["decision"]
        parts.append("<h3>开发者决定与备注</h3><p>" + escape(f"{DECISION_LABELS[decision]} ({decision})") + "</p><pre>" + escape(record["note"] or "未填写备注") + "</pre></section>")
    return "".join(parts)


def _pre(value) -> str:
    return "<pre>" + escape(json.dumps(_public_data(value), ensure_ascii=False, indent=2)) + "</pre>"


def _list(items, ordered=False) -> str:
    tag = "ol" if ordered else "ul"
    return f"<{tag}>" + "".join(f"<li>{escape(str(item))}</li>" for item in items) + f"</{tag}>"


def _image(path, label, run_dir=None) -> str:
    if not path:
        return f"<p>{label}截图未记录。</p>"
    try:
        data = _artifact_path(path, run_dir).read_bytes()
    except OSError:
        return f"<p>{label}截图文件不可用。</p>"
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    if mime not in ("image/png", "image/jpeg", "image/webp"):
        return f"<p>{label}截图格式不支持嵌入。</p>"
    encoded = base64.b64encode(data).decode("ascii")
    return f'<figure><figcaption>{label}</figcaption><img alt="{label}截图" src="data:{mime};base64,{encoded}"></figure>'


class _SummaryParser(HTMLParser):
    """Keep readable report structure, without active markup or any attributes."""

    allowed = {"h1", "h2", "h3", "h4", "p", "section", "div", "span", "strong", "b", "em", "i",
               "small", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "ul", "ol", "li",
               "pre", "code", "blockquote", "a", "br", "hr"}
    discarded = {"script", "style", "iframe", "object", "svg", "math", "template"}
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.blocked = []
        self.open_tags = []

    def handle_starttag(self, tag, attrs):
        if self.blocked or tag in self.discarded:
            if tag not in self.void:
                self.blocked.append(tag)
            return
        if tag in self.allowed:
            self.output.append(f"<{tag}>")
            if tag not in self.void:
                self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        if not self.blocked and tag in self.allowed:
            self.output.append(f"<{tag}>" if tag in self.void else f"<{tag}></{tag}>")

    def handle_endtag(self, tag):
        if self.blocked:
            if tag in self.blocked:
                index = len(self.blocked) - 1 - self.blocked[::-1].index(tag)
                del self.blocked[index:]
            return
        if tag in self.open_tags:
            index = len(self.open_tags) - 1 - self.open_tags[::-1].index(tag)
            while len(self.open_tags) > index:
                self.output.append(f"</{self.open_tags.pop()}>")

    def handle_data(self, data):
        if not self.blocked:
            self.output.append(escape(data))


def _sanitize_summary(fragment: str) -> str:
    parser = _SummaryParser()
    parser.feed(fragment)
    parser.close()
    while parser.open_tags:
        parser.output.append(f"</{parser.open_tags.pop()}>")
    return "".join(parser.output)
