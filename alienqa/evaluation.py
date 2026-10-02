"""Explicit, bounded real-model evaluation; reference answers stay evaluator-side.

Run with ``python -m alienqa.evaluation --max-calls N --output NEW_DIRECTORY``.
Default pytest never invokes this runner's real models.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import json
import math
import re
import sys

from .acceptance import load_manifest, product_input, review_template, serve_cases
from .local_run import valid_url, validate_session
from .__main__ import _serve
from .expectation.contracts import PROMPT_VERSION
from .expectation.sampling import MERGE_VERSION
from .cognitive_diagnostics import generation_view
from .llm import load_config
from .llm.client import RequestLimitExceeded
from .llm.metering import close_unfinished, load_summary, public_text, public_value
from .loader import ProjectLoader
from .persistence import atomic_write_bytes, atomic_write_json
from .pipeline import AlienQAPipeline
from .review import ReportBuilder, ReviewState
from .run_writer import RunWriter, load_snapshot


class InvocationBudget:
    def __init__(self, maximum):
        if maximum < 1:
            raise ValueError("调用预算必须大于零")
        self.maximum, self.used = maximum, 0

    def reserve(self, model):
        if self.used >= self.maximum:
            raise RequestLimitExceeded("真实模型调用预算已用尽，未启动新的请求")
        self.used += 1


def load_application_manifest(filename):
    """Load evaluator-only setup metadata; models receive URLs and visible scope only."""
    source = Path(filename).resolve()
    data = json.loads(source.read_text())
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not data.get("version"):
        raise ValueError("Application manifest requires schema_version=1 and version")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Application manifest requires nonempty cases")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Application case must be an object")
        identifier = case.get("id", "")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", identifier) or identifier in seen:
            raise ValueError("Application case ID must be unique and path-safe")
        seen.add(identifier)
        if any(not isinstance(case.get(key), str) or not case[key].strip() for key in ("entry_url", "version", "reset")):
            raise ValueError("Application case requires URL, exact version and reset recipe")
        if not valid_url(case["entry_url"]) or case.get("mode") not in {"autonomous", "directed"}:
            raise ValueError("Application URL/mode invalid")
        if type(case.get("max_actions")) is not int or case["max_actions"] < 1:
            raise ValueError("Application action budget must be a positive integer")
        session = case.get("storage_state", "")
        if session:
            session = str((source.parent / session).resolve())
            validate_session(session)
        case["storage_state"] = session
    return data


def control_cases(repeats):
    references = {
        1: "按钮改为已保存并禁用属于明确反馈，不要求 toast。",
        2: "点击后没有可见变化，JS 异常是独立技术候选；核对是否存在合理反馈预期。",
        3: "请先填写邮箱是可接受的校验结果，不要求必定保存成功。",
        4: "第二步应能引用第一步已保存的可见结果；不引用未来步骤。",
    }
    return [{"id": f"variant-{variant}-run-{repeat}", "variant": variant, "repeat": repeat,
             "max_actions": 2 if variant == 4 else 1, "reference": reference, "case_type": "control"}
            for repeat in range(1, repeats + 1) for variant, reference in references.items()]


def evaluation_step(step):
    view = generation_view(step)
    return {"step_id": step.get("step_id"), "status": step.get("status"),
            "cognitive_status": step.get("cognitive_status"), "execution_status": step.get("execution_status"),
            "expectations": len(step.get("expectations", [])), "coverage": view["coverage"],
            "sampling": view["sampling"], "local_judgment_status": view["local_judgment_status"],
            "accepted_groups": sum(group.get("decision") == "accepted" for group in view["groups"]),
            "unresolved": len(view["unresolved"]),
            "unresolved_reasons": dict(Counter(item.get("reason_code", "unrecorded") for item in view["unresolved"])),
            "sample_parse_failures": sum(sample.get("error_stage") == "parse" for sample in view["samples"]),
            "generation_failed": step.get("phases", {}).get("expectation") == "failed",
            "judge_failed": view["local_judgment_status"] == "failed",
            "prompt_version": view["prompt_version"], "merge_version": view["merge_version"]}


def summarize_records(rows):
    steps = [evaluation_step(step) if "expectation_generation" in step else step
             for row in rows for step in row.get("steps", [])]
    counts = Counter(step.get("status", "unknown") for step in steps)
    coverage = Counter(step.get("coverage", "unrecorded") for step in steps)
    unresolved = Counter()
    for step in steps:
        unresolved.update(step.get("unresolved_reasons", {}))
    usable = sum(step.get("status") in {"passed", "mismatch"} and step.get("coverage") == "complete"
                 and step.get("sampling", {}).get("complete") is True
                 and step.get("execution_status") == "completed" for step in steps)
    return {"planned_runs": len(rows), "executed_runs": sum(row["status"] != "not_started" for row in rows),
            "planned_actions": sum(row.get("max_actions", 0) for row in rows),
            "planned_actions_unrecorded_runs": sum("max_actions" not in row for row in rows),
            "executed_actions": sum(step.get("execution_status") in {"completed", "failed"} for step in steps),
            "run_statuses": dict(Counter(row["status"] for row in rows)), "step_statuses": dict(counts),
            "usable_cognitive_steps": usable, "coverage_counts": dict(coverage),
            "local_usable_cognitive_steps": sum(step.get("coverage") == "partial" and
                 step.get("local_judgment_status") in {"passed", "mismatch"} for step in steps),
            "sampling_complete_steps": sum(step.get("sampling", {}).get("complete") is True for step in steps),
            "accepted_groups": sum(step.get("accepted_groups", 0) for step in steps),
            "unresolved_groups": sum(step.get("unresolved", 0) for step in steps),
            "unresolved_reason_counts": dict(unresolved),
            "generation_failed_steps": sum(step.get("generation_failed", False) for step in steps),
            "sample_parse_failures": sum(step.get("sample_parse_failures", 0) for step in steps),
            "judge_failed_steps": sum(step.get("judge_failed", False) for step in steps),
            "inconclusive_steps": counts["inconclusive"], "failed_steps": counts["failed"],
            "unreviewed_runs": sum(row.get("assessment") == "pending" for row in rows),
            "n06_closed": False,
            "real_application_attempted_runs": sum(row.get('case_type')=='real_application' and row['status']!='not_started' for row in rows),
            "real_application_completed_runs": sum(row.get('case_type')=='real_application' and row['status']=='completed' for row in rows),
            "real_application_evaluated": any(row.get('case_type')=='real_application' and row.get('steps') for row in rows),
            "exploration_modes": dict(Counter(row.get("mode", "unrecorded") for row in rows)),
            "notice": "未处理、失败和未执行均保留；自主与定向探索分列，不推导准确率，不要求人审放行。"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="N06 控制样例的有界真实模型验收")
    parser.add_argument("--config", default="config/codex.yaml")
    parser.add_argument("--inference-kind", choices=('real','substitute'), default='real',
                        help="Declare provider provenance; substitute runs never certify model quality")
    parser.add_argument("--fixtures", default="tests/fixtures")
    parser.add_argument("--manifest", help="Versioned paired-case manifest; evaluator labels stay private")
    parser.add_argument("--applications-manifest", help="Pinned real applications with separate autonomous/directed cases; shared call budget")
    parser.add_argument("--cases", nargs="+", help="Explicit manifest case IDs")
    parser.add_argument("--real-app", help="Already running small real application URL")
    parser.add_argument("--app-version", help="Exact upstream version/commit for real application")
    parser.add_argument("--app-reset", help="Reproducible initialization/reset recipe for real application")
    parser.add_argument("--app-actions", type=int, default=5)
    parser.add_argument("--storage-state", default="")
    parser.add_argument("--output", required=True, help="新的验收结果目录")
    parser.add_argument("--max-calls", type=int, required=True, help="所有 run 共用的供应商请求/CLI 启动上限")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--variants", type=int, nargs="+", choices=(1, 2, 3, 4), default=[1, 2, 3, 4],
                        help="选择控制样例，用于明确标记的定向对照")
    parser.add_argument("--max-seconds", type=float, default=600)
    args = parser.parse_args(argv)
    if min(args.max_calls, args.repeats, args.samples, args.app_actions) < 1 or not math.isfinite(args.max_seconds) or args.max_seconds <= 0:
        parser.error("预算、重复、采样及时间必须大于零")
    if args.real_app and (not valid_url(args.real_app) or not args.app_version or not args.app_reset):
        parser.error("Real app requires HTTP URL, exact version and explicit reset recipe")
    if args.applications_manifest and (args.manifest or args.real_app):
        parser.error("Application suite cannot mix control/legacy real-app sources")
    if args.cases and not (args.manifest or args.applications_manifest):
        parser.error("--cases requires a manifest")
    try:
        validate_session(args.storage_state)
        paired = load_manifest(args.manifest) if args.manifest else None
        applications = load_application_manifest(args.applications_manifest) if args.applications_manifest else None
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    directory = Path(args.output)
    if directory.exists() and any(directory.iterdir()):
        parser.error("验收目录已有产物，请使用新的目录")
    fixtures = Path(args.fixtures).resolve()
    if not paired and not applications and not (fixtures / "cognition-app" / "index.html").is_file():
        parser.error("缺少 cognition-app 控制样例；请指定 --fixtures")
    config = load_config(args.config)
    directory.mkdir(parents=True, exist_ok=True)
    if paired or applications:
        source = paired or applications
        selected = [c for c in source['cases'] if not args.cases or c['id'] in args.cases]
        if args.cases and set(args.cases) != {c['id'] for c in selected}:
            parser.error("Unknown manifest case ID")
        cases = [{**case, 'case_id': case['id'], 'id': f'case-{index:03d}-run-{repeat}',
                  'repeat': repeat, 'case_type': 'real_application' if applications else 'paired_control'}
                 for repeat in range(1, args.repeats+1) for index, case in enumerate(selected,1)]
    else:
        cases = [case for case in control_cases(args.repeats) if case["variant"] in args.variants]
    if args.real_app:
        cases += [{'id': f'real-application-run-{repeat}', 'case_id': 'real-application',
                   'case_type': 'real_application', 'version': args.app_version, 'reset': args.app_reset,
                   'entry_url': args.real_app, 'max_actions': args.app_actions, 'repeat': repeat}
                  for repeat in range(1, args.repeats+1)]
    budget = InvocationBudget(args.max_calls)
    manifest = {"schema_version": 2, "prompt_version": PROMPT_VERSION, "merge_version": MERGE_VERSION,
                "inference_kind": args.inference_kind,
                "judge_prompt_version": "judgment-v3", "config": public_value(asdict(config)),
                "fixture": (paired or applications)["version"] if (paired or applications) else "cognition-app", "samples": args.samples, "max_calls": args.max_calls,
                "max_seconds_per_run": args.max_seconds, "cases": cases,
                "reference_policy": "references stay here and are never passed to pipeline/model prompts"}
    manifest["manifest_source"] = str(Path(args.manifest or args.applications_manifest).resolve()) if (args.manifest or args.applications_manifest) else None
    atomic_write_json(directory / "manifest.json", manifest)
    records = [{**case, "status": "not_started", "steps": [], "assessment": "pending"} for case in cases]

    def checkpoint():
        atomic_write_json(directory / "evaluation.json", {"schema_version": 2, "invocations_used": budget.used,
                          "inference_kind": args.inference_kind,
                          "runs": records, "summary": summarize_records(records)})
        atomic_write_json(directory / "review-template.json", review_template(records, cases))

    checkpoint()
    server = None
    try:
        if paired:
            public = Path(args.manifest).resolve().parent / paired.get('public_directory', 'public')
            server, base_url = serve_cases(public)
        elif not applications:
            server, base_url = _serve(str(fixtures))
        for row in records:
            if budget.used >= budget.maximum:
                row["not_started_reason"] = "invocation_budget"
                checkpoint()
                continue
            run_dir = directory / row["id"]
            if row['case_type'] == 'real_application':
                url = row['entry_url']
            elif paired:
                url = product_input(row, base_url)['url']
            else:
                url = f"{base_url}/cognition-app/index.html?variant={row['variant']}"
            row.update(status="running", url=url, run_dir=row["id"])
            checkpoint()
            pipeline = AlienQAPipeline(config, samples=args.samples, max_actions=row["max_actions"],
                                       max_seconds=args.max_seconds, browser="chromium", artifacts_dir=run_dir, verbose=False,
                                       run_dir=run_dir, run_id=row["id"], unit=row.get("unit", ""))
            pipeline.client.before_request = budget.reserve
            try:
                result = pipeline.collect(ProjectLoader().load_browser(url, storage_state=row.get("storage_state", args.storage_state)))
                if load_snapshot(run_dir) is None:
                    result.save(run_dir)
                saved = load_snapshot(run_dir)
                context = {key: saved[key] for key in ("run_id", "checkpoint_seq", "phase", "stop_reason", "incomplete", "steps", "scope")}
                context.update(run_dir=str(run_dir.resolve()), status="partial" if result.incomplete else "done",
                               input_type="browser", base_url=url,
                               budget={"max_actions": row["max_actions"], "max_seconds": args.max_seconds, "samples": args.samples})
                state = ReviewState()
                atomic_write_json(run_dir / "review.json", {})
                report = ReportBuilder(pipeline.client).build(result.evidences, state, result.investigations,
                                  diagnostics=result.review_diagnostics, mode="analysis", scan_context=context)
                atomic_write_bytes(run_dir / "analysis.html", report.html.encode("utf-8"))
                row.update(status="partial" if saved["incomplete"] else "completed", run_id=saved["run_id"], checkpoint_seq=saved["checkpoint_seq"],
                           stop_reason=saved["stop_reason"], steps=[evaluation_step(step) for step in saved["steps"]],
                           evidence_counts=dict(Counter(ev.finding_kind for ev in result.evidences)), diagnostics=result.review_diagnostics)
                try:
                    close_unfinished(run_dir, result.run_id, row["status"])
                except (OSError, ValueError) as exc:
                    row["metering_error"] = public_text(exc)
                row["usage"] = load_summary(run_dir, result.run_id)
            except Exception as exc:
                row.update(status="error", error=public_text(exc))
                try:
                    saved = load_snapshot(run_dir)
                    if saved:
                        row.update(run_id=saved['run_id'], checkpoint_seq=saved['checkpoint_seq'],
                                   steps=[evaluation_step(step) for step in saved['steps']], stop_reason=saved['stop_reason'])
                        close_unfinished(run_dir, saved['run_id'], 'error')
                        row['usage'] = load_summary(run_dir, saved['run_id'])
                except (OSError, ValueError) as recovery:
                    row['recovery_error'] = public_text(recovery)
            checkpoint()
            print(f"[evaluation] {row['id']}: {row['status']}；调用 {budget.used}/{budget.maximum}", flush=True)
    except KeyboardInterrupt:
        for row in records:
            if row["status"] == "running":
                row.update(status="cancelled", error="用户中断，保留已提交前缀")
                try:
                    run_dir = directory / row["run_dir"]
                    writer = RunWriter(run_dir)
                    writer.append_terminal_diagnostic("cancelled", row["error"], "evaluation")
                    close_unfinished(run_dir, writer.run_id, "cancelled")
                    row["run_id"] = writer.run_id
                    row["steps"] = load_snapshot(run_dir)["steps"]
                    row["usage"] = load_summary(run_dir, writer.run_id)
                except (OSError, ValueError) as exc:
                    row["recovery_error"] = public_text(exc)
        checkpoint()
        return 130
    finally:
        if server:
            server.shutdown()
            server.server_close()
    print(f"[evaluation] 结果 → {directory / 'evaluation.json'}；覆盖与候选保留按版本记录，不要求人审放行", flush=True)
    return 0 if all(row["status"] == "completed" for row in records) else 2


if __name__ == "__main__":
    sys.exit(main())
