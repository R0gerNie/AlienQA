"""Versioned, bounded expectations and references to frozen visible inputs."""
import re
from copy import deepcopy

from ..evidence.models import valid_basis
from .sampling import MERGE_VERSION, normalize_layout, recognize_feedback, relation
from ..i18n import get_language, normalize_language, t as tr

PROMPT_VERSION = "general-user-v4"
MAX_EXPECTATIONS = 5
MAX_TEXT = 500


def action_parameters(action):
    """Only non-text keyboard commands, never typed/selected values or locators."""
    kind = action.get("type") if isinstance(action, dict) else getattr(action, "type", None)
    if kind != "press":
        return {}
    key = action.get("text") if isinstance(action, dict) else getattr(action, "text", None)
    allowed = {"Enter", "Tab", "Escape", "Space", "Backspace", "Delete", "ArrowUp", "ArrowDown",
               "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"}
    return {"key": key if isinstance(key, str) and key in allowed else None}


def generation_prompt_version(language=None):
    language = get_language() if language is None else normalize_language(language)
    return PROMPT_VERSION + ("-en" if language == "en" else "")


def expression_templates(action_desc, language=None):
    """Optional wording, not inferred requirements or a semantic merge override."""
    english = (get_language() if language is None else normalize_language(language)) == "en"
    kind, _, label = action_desc.partition(" ")
    if kind == "click":
        text = "After this operation, visible result feedback should be provided." if english else "本次操作后应有可见结果反馈"
        return [{"id": "operation.visible_result", "text": text}]
    if not label or label in {"当前控件", "current control", "Unlabeled control"} or len(label) > 200:
        return []
    if kind == "type":
        text = (f'After typing text into "{label}", the input should visibly display the entered content.'
                if english else f"在「{label}」中输入文字后，输入框应可见地显示所输入的内容。")
        return [{"id": "input.visible_content", "text": text}]
    if kind == "blur":
        text = (f'"{label}" should lose input focus and no longer show an active text cursor.'
                if english else f"{label} 失去输入焦点，不再显示活动输入光标。")
        return [{"id": "input.blur_cursor", "text": text}]
    return []


def validate_generation_response(response):
    """Keep legacy envelopes; new abstentions are bounded and noncontradictory."""
    rows = validate_rows(response.get("expectations"))
    abstention = response.get("abstention")
    if abstention is None:
        return rows, None if rows else {"code": "unrecorded", "reason": ""}
    if rows:
        raise ValueError(tr("非空 expectations 不能同时包含 abstention"))
    if (not isinstance(abstention, dict) or set(abstention) != {"code", "reason"}
            or not isinstance(abstention.get("code"), str)
            or abstention.get("code") not in {"insufficient_visible_basis", "no_observable_expectation"}
            or not isinstance(abstention.get("reason"), str)
            or not abstention["reason"].strip() or len(abstention["reason"]) > MAX_TEXT):
        raise ValueError(tr("abstention 必须包含有效 code 和 1～500 字符 reason"))
    return rows, {"code": abstention["code"], "reason": abstention["reason"].strip()}


def validate_rows(rows):
    if not isinstance(rows, list) or len(rows) > MAX_EXPECTATIONS:
        raise ValueError(tr("expectations 必须是最多 5 条的数组"))
    out = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("text"), str):
            raise ValueError(tr("预期文本必须为字符串"))
        text = row["text"].strip()
        basis = row.get("expectation_basis")
        if not text or len(text) > MAX_TEXT or not valid_basis(basis) or len(basis["reference"]) > MAX_TEXT:
            raise ValueError(tr("预期文本或依据无效/超出 500 字符上限"))
        if set(basis) != {"type", "reference"}:
            raise ValueError(tr("依据只能包含 type/reference"))
        out.append({"text": text, "expectation_basis": {"type": basis["type"], "reference": basis["reference"].strip()}})
    return out


def validate_reference(row, frozen):
    basis = row["expectation_basis"]
    reference = basis["reference"]
    if basis["type"] == "visible_copy":
        if not any(reference in text for text in [frozen["visible_text"], *frozen["elements"]]):
            raise ValueError(tr("visible_copy 必须原样引用当前已保存的可见文案/控件"))
    elif basis["type"] == "observed_behavior":
        match = re.fullmatch(r"(ST-\d+):\s*(.+)", reference, flags=re.S)
        if not match or not any(h["step_id"] == match[1] and match[2] in h["visible_result"]
                                for h in frozen["visible_history"]):
            raise ValueError(tr("observed_behavior 必须引用前序已提交步骤及其可见结果原文"))


def merge_samples(samples, *, action_desc="", diagnostics=None):
    """Keep the union; only proven equivalence reduces checks, never disagreement."""
    return _merge_samples(samples, action_desc=action_desc, diagnostics=diagnostics)


def _merge_samples_v2(samples, *, action_desc="", diagnostics=None):
    """Frozen conservative algorithm, exclusively for historical offline replay."""
    return _merge_samples(samples, action_desc=action_desc, diagnostics=diagnostics, historical=True)


def _merge_samples(samples, *, action_desc="", diagnostics=None, historical=False):
    diagnostic = diagnostics if diagnostics is not None else {}
    diagnostic.update(merge_version="sampling-merge-v2.2" if historical else MERGE_VERSION,
                      groups=[], unresolved=[], relationship_warnings=[], coverage="none")
    groups = []
    for sample_index, rows in enumerate(samples):
        if len(rows) > MAX_EXPECTATIONS:
            diagnostic["error_code"] = "sample_limit_exceeded"
            raise ValueError(tr("单份采样超过 5 条上限"))
        for row_index, row in enumerate(rows):
            claim = recognize_feedback(row["text"], action_desc)
            key = ("feedback", claim.facet, claim.positive) if claim else ("literal", normalize_layout(row["text"]))
            group = next((group for group in groups if group["key"] == key), None)
            if group is None:
                group = {"key": key, "claim": claim, "members": [], "reasons": []}
                groups.append(group)
            group["members"].append({"sample_index": sample_index + 1, "row_index": row_index + 1, **deepcopy(row)})

    def row_key(row):
        basis = row["expectation_basis"]
        return row["text"], basis["type"], basis["reference"]

    groups.sort(key=lambda group: min(row_key(member) for member in group["members"]))
    for group in groups:
        representative = min(group["members"], key=row_key)
        group["record"] = {"text": representative["text"], "expectation_basis": deepcopy(representative["expectation_basis"]),
                           "members": group["members"],
                           "support_count": len({m["sample_index"] for m in group["members"]}),
                           "rule_id": group["claim"].rule_id if group["claim"] else "literal.layout",
                           "decision": "accepted", "reason": tr("原文一致或有限规则证明等价；支持数不表示正确率")}
    diagnostic["groups"] = [group["record"] for group in groups]
    if historical and len(groups) > MAX_EXPECTATIONS:
        diagnostic["error_code"] = "merged_limit_exceeded"
        for group in diagnostic["groups"]:
            group.update(decision="not_checked", reason=tr("合并候选超过上限，未交付预期集合"))
        raise ValueError(tr("合并后的预期超过 5 条上限"))

    for index, left in enumerate(groups):
        for right in groups[index + 1:]:
            decision = relation(left["claim"], right["claim"])
            if decision == "compatible":
                continue
            affected = [left, right]
            if historical and decision == "relation_unknown" and len(samples) > 1:
                stable = [g for g in affected if g["record"]["support_count"] == len(samples)]
                # A shared requirement survives an unknown *additional* claim,
                # but two stable unknown claims are not evidence of compatibility.
                if len(stable) == 1:
                    affected = [g for g in affected if g is not stable[0]]
            for group in affected:
                other = right if group is left else left
                group["reasons"].append({"reason_code": decision, "related_text": other["record"]["text"]})

    accepted, unresolved, warnings = [], [], []
    for group in groups:
        record = group["record"]
        if group["reasons"]:
            reason = "conflict" if any(r["reason_code"] == "conflict" for r in group["reasons"]) else "relation_unknown"
            explanation = tr("采样要求互相排斥，均保留检查") if reason == "conflict" else tr("要求关系未知，均保留检查")
            if historical:
                explanation = tr("相同动作的反馈要求互相排斥，需复核") if reason == "conflict" else tr("要求之间的关系超出有限规则，需复核")
            record.update(decision="unresolved" if historical else "accepted", reason=explanation,
                          relations=group["reasons"])
            warning = {"basis": deepcopy(record["expectation_basis"]),
                               "texts": sorted({m["text"] for m in record["members"]}),
                               "members": deepcopy(record["members"]), "reason_code": reason,
                               "reason": explanation, "relations": deepcopy(group["reasons"])}
            (unresolved if historical else warnings).append(warning)
        if not group["reasons"] or not historical:
            accepted.append({"text": record["text"], "expectation_basis": deepcopy(record["expectation_basis"])})
    diagnostic.update(unresolved=unresolved, relationship_warnings=warnings,
                      coverage="partial" if accepted and unresolved else "complete" if accepted else "none")
    return accepted, unresolved
