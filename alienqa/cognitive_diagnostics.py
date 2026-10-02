"""Shared data-only cognition views; legacy records gain no inferred coverage."""
from copy import deepcopy


def step_incomplete(step):
    generation = step.get("expectation_generation", {})
    return (step.get("status") not in {"passed", "mismatch"}
            or generation.get("coverage") in {"none", "partial"}
            or generation.get("sampling", {}).get("complete") is False)


def generation_view(step):
    """Exclude raw responses; parsed provenance and truncation remain visible."""
    generation = step.get("expectation_generation", {})
    return deepcopy({"prompt_version": generation.get("prompt_version", "unrecorded"),
                     "merge_version": generation.get("merge_version", "unrecorded"),
                     "sampling": generation.get("sampling", {}),
                     "coverage": generation.get("coverage", "unrecorded"),
                     "local_judgment_status": step.get("judgment_result", {}).get("status", "unrecorded"),
                     "groups": generation.get("groups", []), "unresolved": generation.get("unresolved", []),
                     "samples": [{key: sample[key] for key in ("sample_index", "call_id", "status", "raw_truncated", "error", "error_stage")
                                  if key in sample} for sample in generation.get("samples", [])],
                     "error": generation.get("error", ""), "error_code": generation.get("error_code", "")})
