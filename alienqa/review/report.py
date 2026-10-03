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
from .report_theme import REPORT_STYLE
from .offline_review import OFFLINE_REVIEW_SCRIPT


def render_report_html(fragment: str, mode="confirmed") -> str:
    """把 LLM 产出的 body 片段包装成带样式的完整 HTML 文档。"""
    return (
        "<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>AlienQA {'QA 与用户认知分析' if mode == 'analysis' else '疑似问题报告'}</title>"
        f"{REPORT_STYLE}</head><body>"
        '<a class="skip-link" href="#report-content">跳到报告内容</a>'
        '<header class="site-header"><div class="brand"><span class="brand-mark" aria-hidden="true">A</span>'
        'AlienQA<span class="header-label">产品体验观察</span></div><span class="header-label">离线报告</span></header>'
        f'<main id="report-content" class="report-shell">{fragment}'
        '<footer class="report-footer"><span>AlienQA · 发现只有内部人才觉得理所当然的地方</span>'
        '<a href="#report-content">回到顶部 ↑</a></footer></main></body></html>'
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
                fragment += '<section class="panel model-supplement"><details><summary>模型编排补充（原始证据以上方记录为准）</summary>' + _sanitize_summary(summary) + "</details></section>"
        if context.get("run_dir") and context.get("run_id"):
            usage = load_summary(context["run_dir"], context["run_id"])
            fragment += '<section class="panel"><h2>LLM 调用与用量</h2><p>已知小计与未知项分别列示，缺少费用不等于免费。</p>'
            if not usage.get("scan_accounting_recorded"):
                fragment += "<p>扫描调用账目未记录；本节只包含后续实际记录的调用，不能当作整次扫描的总成本。</p>"
            fragment += '<details><summary>查看完整调用账目</summary>' + _pre(usage) + '</details></section>'
        fragment += '</div></div>' + OFFLINE_REVIEW_SCRIPT
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
    parts = [f'<div class="report-layout" data-offline-report data-run-id="{escape(str(context.get("run_id", "")), quote=True)}" '
             f'data-report-mode="{escape(mode, quote=True)}"><nav class="report-nav" aria-label="报告目录">'
             '<span class="eyebrow">REPORT INDEX</span><a class="nav-primary" href="#overview">运行概览</a>'
             '<a href="#scope">范围与完整性</a>']
    parts.append('<a href="#findings">发现记录</a>')
    if context.get("steps"):
        parts.append('<a href="#exploration">探索与采样</a>')
    if displayed:
        parts.append('<div class="nav-findings">')
        for index, ev in enumerate(displayed, 1):
            parts.append(f'<a href="#finding-{index}" data-finding-link="{escape(ev.id, quote=True)}"><span class="nav-number">{index:02d}</span>'
                         f'<span>{escape(ev.id)}</span></a>')
        parts.append('</div>')
    parts.append('</nav><div class="report-content"><header id="overview" class="hero">'
                 '<span class="eyebrow">A FRESH PAIR OF EYES</span>'
                 f'<h1>{title}</h1><p class="hero-copy">'
                 + ('从第一次使用你产品的外部用户视角，查看预期与实际体验之间的落差。所有发现均保留，由你选择是否采信。'
                    if mode == 'analysis' else '查看你已选择采信的发现，以及对应的操作、观察和原始记录。')
                 + '</p>')
    if context.get('run_id') or context.get('status'):
        status = context.get('status', '未记录状态')
        labels = {'done': '处理完成', 'completed': '处理完成', 'partial': '部分完成', 'error': '执行失败',
                  'timeout': '运行超时', 'cancelled': '已取消'}
        parts.append('<div class="run-label"><span class="badge badge-neutral">'
                     + escape(labels.get(status, str(status))) + '</span><code>'
                     + escape(str(context.get('run_id', ''))) + '</code></div>')
    stats = ((len(displayed), '本报告展示', f'原扫描共收集 {total} 条发现', 'data-displayed-count'),
             (len(displayed), '本页采信', '默认采信，可逐条调整', 'data-selected-count'),
             (len(context['steps']) if context.get('steps') is not None else '—', '探索步骤', '本次已记录的动作', ''))
    parts.append('<div class="stats">' + ''.join(
        f'<div class="stat"><div class="stat-label">{label}</div><div class="stat-value" {attr}>{value}</div>'
        f'<div class="stat-note">{note}</div></div>' for value, label, note, attr in stats) + '</div>'
        '<div class="offline-toolbar"><p>每条发现默认采信。选择与备注可保存到此浏览器，也可导出；不会修改原扫描记录。</p>'
        '<div class="review-actions"><button type="button" data-review-action="save" disabled>保存全部选择</button>'
        '<button type="button" data-review-action="decisions" disabled>导出决定与备注</button>'
        '<button type="button" class="primary-button" data-review-action="final" disabled>生成最终报告</button></div>'
        '<p data-review-status role="status">当前默认全部采信；最终报告只包含采信的发现。</p></div>'
        '<noscript><p class="warning">浏览器未启用 JavaScript：可以阅读原始报告，启用后可保存选择并导出最终报告。</p></noscript></header>')
    metadata = {key: context[key] for key in ("run_id", "status", "input_type", "base_url", "started_at", "finished_at",
                "checkpoint_seq", "phase", "stop_reason", "incomplete", "scope", "budget", "data_status", "source_context") if key in context}
    if metadata:
        metadata.setdefault("budget", "未记录运行预算")
    parts.append('<section id="scope" class="panel"><div class="section-heading"><h2>扫描范围与完整性</h2>'
                 '<span class="eyebrow">SCAN CONTEXT</span></div>'
                 '<p class="section-description">结果对应本次探索的范围；处理完成不代表已覆盖整个产品。</p>')
    if metadata:
        labels = (('base_url', '被测应用'), ('input_type', '输入方式'), ('started_at', '开始时间'),
                  ('finished_at', '结束时间'), ('stop_reason', '停止原因'), ('budget', '运行预算'))
        parts.append('<dl class="metadata">' + ''.join(
            '<div><dt>' + label + '</dt><dd>' + escape(
                json.dumps(metadata[key], ensure_ascii=False) if isinstance(metadata[key], (dict, list)) else str(metadata[key])
            ) + '</dd></div>' for key, label in labels if key in metadata) + '</dl>')
        parts.append('<details><summary>查看完整运行记录</summary>' + _pre(metadata) + '</details>')
    else:
        parts.append('<p>旧记录：扫描范围及完整性未记录。</p>')
    if diagnostics or context.get("incomplete") or context.get("status") in {"partial", "error", "timeout", "cancelled"}:
        parts.append('<div class="warning"><strong>扫描不完整</strong>：执行或判断有失败、缺失或提前终止，不能将未发现问题视为通过。'
                     '<details><summary>查看诊断记录</summary>' + _pre(diagnostics or []) + '</details></div>')
    parts.append('</section>')
    exploration = []
    if context.get("steps"):
        fields = ("step_id", "action_id", "action", "status", "execution_status", "cognitive_status", "error", "execution", "interaction_coverage", "trajectory")
        exploration.append('<section id="exploration" class="panel"><div class="section-heading"><h2>探索与采样</h2>'
                     '<span class="eyebrow">EXPLORATION LOG</span></div>'
                     '<p class="section-description">逐步查看事前要求、采样来源和仍无法判断的部分。</p>'
                     '<details><summary>探索步骤 · 查看原始动作记录</summary>'
                     + _pre([{k: s[k] for k in fields if k in s} for s in context["steps"]]) + '</details>')
        exploration.append('<h3>认知采样与未决要求</h3>')
        for step in context["steps"]:
            view = generation_view(step)
            coverage = "未记录" if view["coverage"] == "unrecorded" else view["coverage"]
            local = "未记录" if view["local_judgment_status"] == "unrecorded" else view["local_judgment_status"]
            exploration.append('<details><summary><span class="step-heading"><span>'
                         + escape(str(step.get('step_id', '未记录步骤'))) + '</span><small>覆盖：'
                         + escape(coverage) + ' · 判定：' + escape(local) + '</small></span></summary>')
            exploration.append("<p>检查覆盖：" + escape(coverage) + "；局部判定：" + escape(local) + "</p>")
            if view["coverage"] == "partial":
                exploration.append('<p class="warning">部分要求仍未决，局部判定不代表完整通过。</p>')
            if view["unverifiable_expectation_ids"]:
                exploration.append("<p>另有无法判断的要求；已产生的落差仍保留。</p>" + _pre(view["unverifiable_expectation_ids"]))
            if view["relationship_warnings"]:
                exploration.append("<p>采样关系备注：全部候选仍交付检查。</p>" + _pre(view["relationship_warnings"]))
            if view["sampling"]:
                exploration.append("<p>采样完成情况</p>" + _pre(view["sampling"]))
            else:
                exploration.append("<p>旧记录：采样完成情况未记录。</p>")
            exploration.append("<p>事前采样要求与未决原因</p>" + _pre(view))
            exploration.append('</details>')
        exploration.append('</section>')
    parts.append('<div id="findings"><div class="section-heading"><h2>发现记录</h2>'
                 f'<span class="badge badge-neutral" data-findings-count>{len(displayed)} 条发现</span></div>')
    if not total:
        parts.append('<p class="empty-state">未记录发现；此结果不代表已覆盖所有功能或证明产品无问题。</p>')
    elif not displayed:
        parts.append('<p class="empty-state">本次没有人工采信的证据；此结果不代表已覆盖所有功能或证明产品无问题。</p>')
    for index, ev in enumerate(displayed, 1):
        inv = inv_map.get(ev.issue_id)
        members = getattr(inv, "evidence_ids", []) or []
        if members and ev.id not in members:
            inv = None
        record = _evidence_dict(ev, inv, context.get("run_dir"), state, context)
        kind = {'technical_anomaly': '技术信号', 'cognitive_mismatch': '用户认知落差'}.get(ev.finding_kind, '发现')
        parts.append(f'<section class="finding" id="{escape(ev.id, quote=True)}">'
                     f'<div class="finding-heading" id="finding-{index}"><span class="finding-number">FINDING {index:02d}</span>'
                     f'<span class="badge badge-{escape(ev.severity.value, quote=True)}">{escape(ev.severity.value)}</span>'
                     f'<span class="badge badge-neutral">{kind}</span></div>'
                     f'<h2 class="finding-title">{escape(ev.id)}</h2>')
        expectation = ev.expectation or ('技术候选：认知预期不适用' if ev.finding_kind == 'technical_anomaly' else '未记录')
        parts.append('<div class="comparison"><div><h3>事前预期</h3><p>' + escape(expectation)
                     + '</p></div><div><h3>观察摘要</h3><p>' + escape(ev.observation_summary or '未记录') + '</p></div></div>')
        if ev.reasoning:
            parts.append('<p class="reasoning"><strong>模型推理 · </strong>' + escape(ev.reasoning) + '</p>')
        parts.append('<h3>动作前后截图</h3><div class="screenshots">')
        for name, label in (("before", "动作前"), ("after", "动作后")):
            parts.append(_image((ev.artifacts or {}).get(name), label, context.get("run_dir")))
        parts.append('</div><details><summary>查看原始记录、复现步骤与技术信号</summary>')
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
        parts.append('<details class="recorded-decision"><summary>生成时的决定与备注（原扫描快照） · '
                     + escape(DECISION_LABELS[decision]) + '</summary><p>'
                     + escape(f'{DECISION_LABELS[decision]} ({decision})') + '</p><pre>'
                     + escape(record['note'] or '未填写备注') + '</pre></details></details>'
                     f'<div class="review-controls" data-offline-review="{escape(ev.id, quote=True)}">'
                     f'<label for="choice-{index}">是否采信<select id="choice-{index}" aria-label="是否采信">'
                     '<option value="confirmed" selected>采信</option><option value="rejected">不采信</option></select></label>'
                     f'<label for="note-{index}">备注<textarea id="note-{index}" aria-label="备注" rows="3">'
                     + escape(record['note']) + '</textarea></label><div class="review-row-actions">'
                     '<button type="button" disabled>保存此条</button><span role="status">默认采信 · 尚未保存到此浏览器</span>'
                     '</div></div></section>')
    parts.append('</div>')
    parts.extend(exploration)
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
