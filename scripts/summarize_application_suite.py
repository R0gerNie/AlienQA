"""Reconcile all attempts and mechanical candidate delivery, without human/precision gates."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alienqa.llm.jsonutil import loads_object
from alienqa.llm.metering import load_summary
from alienqa.persistence import atomic_write_json


def audit_run(directory):
    directory = Path(directory)
    snapshot = json.loads((directory / "scan.json").read_text())
    evidence = snapshot.get("evidences", [])
    report = (directory / "analysis.html").read_text() if (directory / "analysis.html").is_file() else ""
    result = {"source_candidates": 0, "preserved_source_members": 0, "merged_requirements": 0,
              "requirements_enrolled": 0, "missing_source_members": [], "groups_not_enrolled": [],
              "judged_mismatches": 0, "mismatches_without_evidence": [], "unknown_requirements": 0,
              "evidences": len(evidence), "report_present": bool(report),
              "evidences_missing_from_report": [row["id"] for row in evidence if row["id"] not in report]}
    for step in snapshot.get("steps", []):
        generation = step.get("expectation_generation", {})
        source = {(sample["sample_index"], index) for sample in generation.get("samples", [])
                  for index, row in enumerate(sample.get("parsed", []), 1)}
        groups = generation.get("groups", [])
        members = {(member["sample_index"], member["row_index"]) for group in groups for member in group.get("members", [])}
        enrolled = {row["id"] for row in step.get("expectations", [])}
        result["source_candidates"] += len(source)
        result["preserved_source_members"] += len(source & members)
        result["merged_requirements"] += len(groups)
        result["requirements_enrolled"] += len(enrolled)
        result["missing_source_members"] += [[step["step_id"], *key] for key in sorted(source - members)]
        result["groups_not_enrolled"] += [[step["step_id"], group.get("expectation_id")]
                                        for group in groups if group.get("expectation_id") not in enrolled]
        result["unknown_requirements"] += len(step.get("judgment_result", {}).get("unverifiable_expectation_ids", []))
        successful = [row for row in step.get("judgment_outputs", []) if row.get("status")]
        if successful:
            mismatches = loads_object(successful[-1]["raw"]).get("mismatches", [])
            result["judged_mismatches"] += len(mismatches)
            saved = {row.get("expectation_id") for row in evidence if row.get("step_id") == step["step_id"]}
            result["mismatches_without_evidence"] += [[step["step_id"], row.get("expectation_id")]
                for row in mismatches if row.get("expectation_id") not in saved]
    return result


def summarize(directory):
    directory = Path(directory)
    evaluation = json.loads((directory / "evaluation.json").read_text())
    results, roles = [], Counter()
    attempts = prompt = completion = unknown_cost = 0
    counts = Counter()
    for row in evaluation["runs"]:
        current = {"case_id": row["case_id"], "mode": row.get("mode"), "status": row["status"]}
        run = directory / row["id"]
        if (run / "scan.json").is_file():
            current.update(audit_run(run))
            snapshot = json.loads((run / "scan.json").read_text())
            usage = load_summary(run, snapshot["run_id"])
            current["usage"] = usage
            attempts += usage.get("attempts", 0)
            counts.update(usage.get("counts", {}))
            prompt += usage.get("tokens", {}).get("prompt_tokens", {}).get("known", 0)
            completion += usage.get("tokens", {}).get("completion_tokens", {}).get("known", 0)
            unknown_cost += usage.get("unknown_cost_attempts", 0)
            roles.update({role: values["attempts"] for role, values in usage.get("by_role", {}).items()})
        results.append(current)
    return {"schema_version": 1, "runs": results, "planned_runs": len(evaluation["runs"]),
            "accounting_complete": all(row["status"] != "running" for row in evaluation["runs"]),
            "invocations_used": evaluation["invocations_used"], "metered_attempts": attempts,
            "invocations_match_attempts": attempts == evaluation["invocations_used"], "by_role": dict(roles),
            "attempt_statuses": dict(counts), "known_prompt_tokens": prompt, "known_completion_tokens": completion,
            "unknown_cost_attempts": unknown_cost, "human_review_required": False,
            "notice": "No inference about precision or complete exploration. Cost details remain per-run; missing costs are unknown."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    args = parser.parse_args()
    result = summarize(args.directory)
    output = Path(args.directory) / "accounting-reconciliation.json"
    atomic_write_json(output, result)
    print(output)
