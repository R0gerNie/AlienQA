"""Versioned, bounded expectations and references to frozen visible inputs."""
import re
from copy import deepcopy

from ..evidence.models import valid_basis
from .sampling import MERGE_VERSION, normalize_layout, recognize_feedback, relation

PROMPT_VERSION = "general-user-v2"
MAX_EXPECTATIONS = 5
MAX_TEXT = 500


def validate_rows(rows):
    if not isinstance(rows, list) or len(rows) > MAX_EXPECTATIONS:
        raise ValueError("expectations 必须是最多 5 条的数组")
    out = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("text"), str):
            raise ValueError("预期文本必须为字符串")
        text = row["text"].strip()
        basis = row.get("expectation_basis")
        if not text or len(text) > MAX_TEXT or not valid_basis(basis) or len(basis["reference"]) > MAX_TEXT:
            raise ValueError("预期文本或依据无效/超出 500 字符上限")
        if set(basis) != {"type", "reference"}:
            raise ValueError("依据只能包含 type/reference")
        out.append({"text": text, "expectation_basis": {"type": basis["type"], "reference": basis["reference"].strip()}})
    return out


def validate_reference(row, frozen):
    basis = row["expectation_basis"]
    reference = basis["reference"]
    if basis["type"] == "visible_copy":
        if not any(reference in text for text in [frozen["visible_text"], *frozen["elements"]]):
            raise ValueError("visible_copy 必须原样引用当前已保存的可见文案/控件")
    elif basis["type"] == "observed_behavior":
        match = re.fullmatch(r"(ST-\d+):\s*(.+)", reference, flags=re.S)
        if not match or not any(h["step_id"] == match[1] and match[2] in h["visible_result"]
                                for h in frozen["visible_history"]):
            raise ValueError("observed_behavior 必须引用前序已提交步骤及其可见结果原文")


def merge_samples(samples, *, action_desc="", diagnostics=None):
    """Action-scoped relationships with original rows and explicit provenance."""
    diagnostic = diagnostics if diagnostics is not None else {}
    diagnostic.update(merge_version=MERGE_VERSION, groups=[], unresolved=[], coverage="none")
    groups = []
    for sample_index, rows in enumerate(samples):
        if len(rows) > MAX_EXPECTATIONS:
            diagnostic["error_code"] = "sample_limit_exceeded"
            raise ValueError("单份采样超过 5 条上限")
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
                           "decision": "accepted", "reason": "原文一致或有限规则证明等价；支持数不表示正确率"}
    diagnostic["groups"] = [group["record"] for group in groups]
    if len(groups) > MAX_EXPECTATIONS:
        diagnostic["error_code"] = "merged_limit_exceeded"
        for group in diagnostic["groups"]:
            group.update(decision="not_checked", reason="合并候选超过上限，未交付预期集合")
        raise ValueError("合并后的预期超过 5 条上限")

    for index, left in enumerate(groups):
        for right in groups[index + 1:]:
            decision = relation(left["claim"], right["claim"])
            if decision == "compatible":
                continue
            affected = [left, right]
            if decision == "relation_unknown" and len(samples) > 1:
                stable = [g for g in affected if g["record"]["support_count"] == len(samples)]
                # A shared requirement survives an unknown *additional* claim,
                # but two stable unknown claims are not evidence of compatibility.
                if len(stable) == 1:
                    affected = [g for g in affected if g is not stable[0]]
            for group in affected:
                other = right if group is left else left
                group["reasons"].append({"reason_code": decision, "related_text": other["record"]["text"]})

    accepted, unresolved = [], []
    for group in groups:
        record = group["record"]
        if group["reasons"]:
            reason = "conflict" if any(r["reason_code"] == "conflict" for r in group["reasons"]) else "relation_unknown"
            explanation = "相同动作的反馈要求互相排斥，需复核" if reason == "conflict" else "要求之间的关系超出有限规则，需复核"
            record.update(decision="unresolved", reason=explanation, relations=group["reasons"])
            unresolved.append({"basis": deepcopy(record["expectation_basis"]),
                               "texts": sorted({m["text"] for m in record["members"]}),
                               "members": deepcopy(record["members"]), "reason_code": reason,
                               "reason": explanation, "relations": deepcopy(group["reasons"])})
        else:
            accepted.append({"text": record["text"], "expectation_basis": deepcopy(record["expectation_basis"])})
    diagnostic.update(unresolved=unresolved, coverage="partial" if accepted and unresolved else "complete" if accepted else "none")
    return accepted, unresolved
