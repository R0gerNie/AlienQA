"""Offline historical/current replay. No inference, IDs or Evidence."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from .contracts import merge_samples, _merge_samples_v2, validate_rows
from .sampling import MERGE_VERSION
from ..persistence import atomic_write_json


def _legacy_merge(samples):
    """Frozen sampling-merge-v1 baseline, used only by this offline evaluator."""
    groups = {}
    for index, rows in enumerate(samples):
        for row in rows:
            basis = row["expectation_basis"]
            groups.setdefault((basis["type"], basis["reference"]), {}).setdefault(index, {})[row["text"]] = row
    accepted, unresolved = {}, []
    for key, per_sample in groups.items():
        sets = [set(rows) for rows in per_sample.values()]
        if any(texts != sets[0] for texts in sets[1:]):
            unresolved.append({"basis": {"type": key[0], "reference": key[1]}, "texts": sorted(set().union(*sets)),
                               "reason": "同一依据的采样预期不同，需复核"})
            continue
        for row in next(iter(per_sample.values())).values():
            prior = accepted.get(row["text"])
            if prior and prior["expectation_basis"] != row["expectation_basis"]:
                raise ValueError("同一预期有不同依据，无法唯一关联")
            accepted[row["text"]] = row
    if len(accepted) > 5:
        raise ValueError("合并后的预期超过 5 条上限")
    return [accepted[text] for text in sorted(accepted)], unresolved


def _version_result(samples, action, version):
    result = {"merge_version": version}
    try:
        if version == "sampling-merge-v1":
            accepted, unresolved = _legacy_merge(samples)
            result["coverage"] = "partial" if accepted and unresolved else "complete" if accepted else "none"
        elif version == "sampling-merge-v2.2":
            accepted, unresolved = _merge_samples_v2(samples, action_desc=action, diagnostics=result)
        else:
            accepted, unresolved = merge_samples(samples, action_desc=action, diagnostics=result)
        result.update(accepted=accepted, unresolved=unresolved, status="completed")
    except ValueError as exc:
        result.update(status="failed", error=str(exc), coverage="none", accepted=[])
    return result


def compare_corpus(corpus):
    records = []
    for case in corpus["cases"]:
        record = {"id": case["id"], "action": case.get("action", ""), "annotation": deepcopy(case.get("annotation", {}))}
        try:
            # Response envelopes require complete parsed rows. Never repair or
            # infer expectations from a truncated raw response in evaluation.
            samples = [validate_rows(sample["parsed"] if isinstance(sample, dict) else sample) for sample in case["samples"]]
            if not samples:
                raise ValueError("没有可回放的完整采样")
            record.update(status="completed", v1=_version_result(samples, record["action"], "sampling-merge-v1"),
                          v2=_version_result(samples, record["action"], "sampling-merge-v2.2"),
                          current=_version_result(samples, record["action"], MERGE_VERSION))
        except (ValueError, TypeError, KeyError) as exc:
            record.update(status="input_failed", error=str(exc))
        records.append(record)
    summary = {"cases": len(records), "input_failed": sum(row["status"] == "input_failed" for row in records),
               "v1_accepted_cases": sum(bool(row.get("v1", {}).get("accepted")) for row in records),
               "v2_accepted_cases": sum(bool(row.get("v2", {}).get("accepted")) for row in records),
               "current_accepted_cases": sum(bool(row.get("current", {}).get("accepted")) for row in records),
               "current_merge_version": MERGE_VERSION,
               "independent_review_pending": sum(row["annotation"].get("independent_review") != "completed" for row in records),
               "model_invocations": 0, "expectation_ids_created": 0, "evidence_created": 0}
    return {"schema_version": 2, "purpose": "offline_merge_comparison", "cases": records, "summary": summary,
            "notice": "同一保存采样的算法回放；不改写历史运行、不产生认知判断，不代表真实用户准确率或独立人工验收。"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="N03 已保存采样的新旧合并规则离线对照（零模型调用）")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.exists():
        parser.error("输出已有产物，请使用新文件，不能覆盖历史对照")
    result = compare_corpus(json.loads(Path(args.corpus).read_text(encoding="utf-8")))
    atomic_write_json(output, result)
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 2 if result["summary"]["input_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
