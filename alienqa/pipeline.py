"""AlienQA 全链路编排器：把 01→12 串成一条流水线，产出 HTML 报告。

这是正式入口（`python -m alienqa`）背后的引擎：任何 CLI / API / 定时任务
都调用 AlienQAPipeline.run()，不再散落脚本。
"""
from __future__ import annotations

import tempfile
import time
import sqlite3
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from copy import deepcopy
from pathlib import Path

from .context import ExplorationContext
from .context.models import Observation as CtxObservation
from .dedup import Deduplicator
from .driver import PlaywrightDriver
from .evidence import EvidenceEngine
from .evidence.storage import EvidenceStore
from .evidence.models import Evidence, valid_basis
from .expectation import ExpectationEngine, JudgmentError, PageInfo
from .cognitive_diagnostics import step_incomplete
from .investigation import Investigation, InvestigationAgent
from .llm import LLMClient, LLMConfig
from .loader import Project, UnitLocator, UnitScope, is_all_unit
from .mapper import ProductMapper, ProductMap
from .observation import ObservationEngine, Observation, RuntimeObservation
from .persistence import atomic_write_bytes
from .run_writer import RunWriter, StorageError, load_snapshot
from .planner import ActionPlanner, ExploreBudget
from .llm.metering import MeteringSink
from .review import Decision, HumanReview, Report, ReportBuilder, ReviewState
from .state import StateTracker
from .i18n import language_context, normalize_language, t as tr


def _join_focus(unit: str, instructions: str, language=None) -> str:
    parts = []
    if unit:
        parts.append(tr("单元：{unit}", language, unit=unit))
    if instructions:
        parts.append(tr("指令：{instructions}", language, instructions=instructions))
    return "\n".join(parts)


@dataclass
class PipelineResult:
    """一次全链路运行的产物。"""

    report: Report | None = None
    evidences: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    investigations: list = field(default_factory=list)
    states: list = field(default_factory=list)
    scope: UnitScope | None = None
    steps: list[dict] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    stop_reason: str = ""
    run_id: str = ""
    raw_refs: list[dict] = field(default_factory=list)
    run_dir: str = ""
    access_result: dict | None = None
    language: str = "zh"

    @property
    def html(self) -> str:
        return self.report.html if self.report else ""

    @property
    def incomplete(self) -> bool:
        return bool(self.diagnostics) or any(step_incomplete(step) for step in self.steps)

    @property
    def review_diagnostics(self) -> list[dict]:
        return list(self.diagnostics) + [
            {"stage": "exploration", "step": step.get("index"),
             "status": step.get("status"), "error": step.get("error", "")}
            for step in self.steps if step_incomplete(step)
        ]

    def save(self, directory: str | Path) -> None:
        """持久化采集与诊断，即使尚未人工审核也保留可检查的运行结果。"""
        writer = RunWriter(directory, self.run_id or None)
        self.run_id = writer.run_id
        writer.checkpoint(phase="terminal", steps=self.steps, evidences=self.evidences,
                          diagnostics=self.diagnostics, raw_refs=self.raw_refs,
                          investigations=self.investigations, stop_reason=self.stop_reason,
                          scope={**asdict(self.scope), "language": self.language} if self.scope else None,
                          issues=self.issues, access_result=self.access_result, language=self.language)


class AlienQAPipeline:
    """01(装载由调用方完成) → 02→12 的编排器。

    参数：
    - config: 从 config.yaml 载入的 LLMConfig（六角色模型/温度/回退）。
    - samples: 08 预期生成的采样次数。
    - headless: 浏览器是否无头运行。
    - max_actions: 探索动作上限（保护性预算）。
    - artifacts_dir: 证据截图/技术信号落盘目录（None=临时目录）。
    - auto_confirm: 是否自动采信全部证据（CLI 演示模式；人工终审走 WebUI）。
    - focus: 单元扫描的聚焦指令（单元名 + 针对该单元的要求），注入 08 预期生成。
    - unit / instructions: 单元定位器的输入；给出后会先圈定单元范围再探索。
    - browser: 浏览器偏好，"chrome"（默认，系统 Google Chrome，不可用时回退 Chromium）或 "chromium"。
    """

    def __init__(
        self,
        config: LLMConfig,
        samples: int = 2,
        headless: bool = True,
        max_actions: int = 10,
        artifacts_dir: str | Path | None = None,
        auto_confirm: bool = False,
        focus: str = "",
        unit: str = "",
        instructions: str = "",
        verbose: bool = True,
        browser: str = "chrome",
        max_seconds: float = 300,
        run_dir: str | Path | None = None,
        run_id: str | None = None,
    ):
        self.language = normalize_language(getattr(config, "language", "zh"))
        if max_actions < 1 or max_seconds <= 0 or samples < 1:
            raise ValueError(tr("动作数、采样次数及时间预算必须大于零", self.language))
        self.client = LLMClient(config)
        self.samples = samples
        self.headless = headless
        self.max_actions = max_actions
        self.artifacts_dir = artifacts_dir
        self.auto_confirm = auto_confirm
        self.unit = unit
        self.instructions = instructions
        self.focus = focus or _join_focus(unit, instructions, self.language)
        self.verbose = verbose
        self.browser = browser
        self.max_seconds = max_seconds
        self.run_dir = run_dir
        self.run_id = run_id

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    def collect(self, project: Project) -> PipelineResult:
        with language_context(self.language):
            return self._collect(project)

    def _collect(self, project: Project) -> PipelineResult:
        """Collect into one run-local, incrementally committed scan."""
        directory = Path(self.run_dir or self.artifacts_dir or tempfile.mkdtemp(prefix="alienqa_"))
        self._writer = RunWriter(directory, self.run_id)
        if self._writer.seq:
            raise ValueError(tr("结果目录已有扫描，请为新 run 使用新的目录"))
        self._result = PipelineResult(run_id=self._writer.run_id, run_dir=str(directory), language=self.language)
        if isinstance(self.client, LLMClient):
            self.client.sink = MeteringSink(directory, self._writer.run_id)
            self.client.on_metering_error = lambda message: self._diagnostic("metering", message)
            self.client._record("initialize", self.client.config)
        artifacts = Path(self.artifacts_dir or directory / "artifacts")
        self._evidence = EvidenceEngine(artifacts, EvidenceStore(directory / "evidence.db"))
        self._project = project
        self._runtime_before = None
        self._checkpoint("entry")
        try:
            if project.input_type == "browser":
                return self._collect_browser(project)
            return self._collect_source(project)
        except StorageError as exc:
            try:
                self._writer.append_terminal_diagnostic("storage_failed", str(exc), "storage")
            except StorageError:
                pass  # the previous committed prefix is still authoritative
            raise
        except Exception as exc:
            self._diagnostic("scan", exc)
            self._result.stop_reason = "error"
            self._checkpoint("terminal")
            return self._result
        finally:
            if isinstance(self.client, LLMClient):
                self.client._record("write_summary")

    def _checkpoint(self, phase):
        result = self._result
        self._writer.checkpoint(phase=phase, steps=result.steps, evidences=result.evidences,
                                diagnostics=result.diagnostics, raw_refs=result.raw_refs,
                                investigations=result.investigations, stop_reason=result.stop_reason,
                                scope={**asdict(result.scope), "language": self.language} if result.scope else None,
                                issues=result.issues, access_result=result.access_result, language=self.language)
        if isinstance(self.client, LLMClient):
            step = result.steps[-1] if result.steps and phase in {"expectation", "visual", "judgment", "action", "raw_capture"} else {}
            ref = f"scan.json#steps/{step['step_id']}" if step else "scan.json"
            if phase == "expectation" and step:
                ref += "/input/cognitive"
            self.client.set_context(phase=phase, step_id=step.get("step_id"), action_id=step.get("action_id"), input_ref=ref)

    def _diagnostic(self, stage, error, step=None):
        self._result.diagnostics.append({"stage": stage, "step_id": step.get("step_id") if step else None,
                                         "error": str(error)})

    def _runtime_context(self, driver, phase, step=None):
        if hasattr(driver, "set_runtime_context"):
            driver.set_runtime_context(run_id=self._writer.run_id,
                                       step_id=step.get("step_id") if step else None,
                                       action_id=step.get("action_id") if step else None, phase=phase)

    def _capture_runtime(self, driver, phase, action=None, step=None, state=None):
        try:
            runtime = ObservationEngine(self.client).observe_runtime(driver, self._runtime_before)
            self._runtime_before = deepcopy(driver.collect_runtime())
        except Exception as exc:
            self._diagnostic("runtime", exc, step)
            self._checkpoint("raw_capture")
            return None, []
        # The boundary is frozen now; visual/model latency cannot expand it.
        for record in runtime.records:
            record.update(run_id=self._writer.run_id, step_id=step.get("step_id") if step else None,
                          action_id=step.get("action_id") if step else None, phase=phase)
        if runtime.records or runtime.window.get("dropped_count") or phase in ("entry", "action"):
            ref = self._writer.save_raw({"records": runtime.records, "window": runtime.window}, phase=phase)
            self._result.raw_refs.append(ref)
            if step is not None:
                step["raw_refs"] = [ref]
                step["source_record_ids"] = ref["record_ids"]
            if runtime.window.get("dropped_count"):
                self._diagnostic("runtime", tr("原始事件超过上限，丢弃 {count} 条", count=runtime.window["dropped_count"]), step)
            self._checkpoint("raw_capture" if phase == "action" else phase)
            evs = self._evidence.build_technical(runtime, action, state, driver, before_state=state,
                                                 run_id=self._writer.run_id,
                                                 step_id=step.get("step_id") if step else None,
                                                 action_id=step.get("action_id") if step else None)
            for ev in evs:
                self._persist_evidence(ev)
            self._result.evidences.extend(evs)
            if step is not None:
                step["evidence_ids"].extend(e.id for e in evs)
            self._checkpoint("raw_capture" if phase == "action" else phase)
            return runtime, evs
        return runtime, []

    def _persist_evidence(self, evidence):
        if self._project.artifacts.get("static_server"):
            evidence.replay["static_server"] = dict(self._project.artifacts["static_server"])
        if not evidence.replay.get("url"):
            evidence.replay["url"] = self._project.base_url
        try:
            self._evidence.persist(evidence)
        except (OSError, sqlite3.Error) as exc:
            raise StorageError(f"evidence storage_failed: {exc}", "storage_failed") from exc

    def _collect_source(self, project: Project) -> PipelineResult:
        return self._collect_project(project, browser_mode=False)

    def _collect_browser(self, project: Project) -> PipelineResult:
        return self._collect_project(project, browser_mode=True)

    def _collect_project(self, project, browser_mode):
        driver = PlaywrightDriver(headless=self.headless, browser=self.browser)
        try:
            self._runtime_context(driver, "entry")
            try:
                driver.launch(project.base_url, storage_state=project.storage_state or None)
                self._result.access_result = deepcopy(getattr(driver, "access_result", None))
            except Exception as exc:
                self._diagnostic("launch", exc)
                self._capture_runtime(driver, "entry")
                self._result.stop_reason = "error"
                self._checkpoint("terminal")
                return self._result
            self._capture_runtime(driver, "entry")
            self._runtime_context(driver, "background")
            try:
                pm = self._map_from_browser(driver, project) if browser_mode else ProductMapper(self.client).map(project)
                mapped = True
            except Exception as exc:
                self._diagnostic("map", exc)
                pm, mapped = ProductMap(), False
            self._checkpoint("entry")
            return self._collect_live(driver, project, pm, mapped=mapped)
        finally:
            driver.close()

    def _map_from_browser(self, driver, project) -> ProductMap:
        """02b：用浏览器可见文字建立产品地图（黑盒，无源码）。"""
        self._log(tr("[02b] 读取浏览器可见文字…"))
        surface = (driver.visible_text() or "").strip()
        if not surface:
            self._log(tr("[02b] 页面无可见文字，返回空 ProductMap"))
            return ProductMap()
        pm = ProductMapper(self.client).map_from_browser(project, surface)
        self._log(tr("[02b] 主旨: {brief}", brief=pm.brief[:160]))
        self._log(tr("[02b] 功能区域: {count} 个", count=len(pm.areas)))
        return pm

    def run(self, project: Project, output_path: str | Path | None = None) -> PipelineResult:
        with language_context(self.language):
            return self._run(project, output_path)

    def _run(self, project: Project, output_path: str | Path | None = None) -> PipelineResult:
        """01→12：collect 之后按 auto_confirm 采信，再生成最终报告。"""
        result = self.collect(project)
        if result.run_dir:
            result.save(result.run_dir)
        review = HumanReview(ReviewState())
        if self.auto_confirm:
            for ev in result.evidences:
                review.decide(ev.id, Decision.CONFIRMED, tr("CLI 自动采信"))
        elif result.evidences:
            self._log(tr("[12] 证据待人工审核；未生成正式报告"))
            return result
        self._log(tr("[12] 生成 HTML 报告中…"))
        report = ReportBuilder(self.client).build(
            result.evidences, review.state, result.investigations,
            diagnostics=result.review_diagnostics, language=self.language,
        )
        if output_path:
            Path(output_path).write_text(report.html, encoding="utf-8")
            self._log(tr("[12] 报告已写入 {path}（采信 {accepted}/{total}）", path=output_path, accepted=report.accepted_count, total=report.total_count))
        result.report = report
        return result

    def _collect_live(self, driver, project, pm, mapped=True) -> PipelineResult:
        result = self._result
        exp_engine = ExpectationEngine(self.client, samples=self.samples)
        obs_engine = ObservationEngine(self.client)
        planner = ActionPlanner(ExploreBudget(max_steps=self.max_actions))
        tracker = StateTracker()
        builder = ExplorationContext()
        started = time.monotonic()
        deadline = started + self.max_seconds
        if hasattr(driver, "set_deadline"):
            driver.set_deadline(deadline)
        coverage_warnings = set()
        action_attempts = {}
        state = tracker.capture(driver)
        result.states = tracker.sequence()
        if not is_all_unit(self.unit):
            try:
                scope = UnitLocator(self.client).locate(self.unit, self.instructions, pm.brief,
                                                        driver.interactive_elements())
            except Exception as exc:
                self._diagnostic("unit_locator", exc)
                scope = None
            result.scope = scope
            if scope is None or scope.is_empty():
                self._diagnostic("unit_locator", tr("未定位到指定单元，未扩大为全量扫描"))
                result.stop_reason = "scope_not_found"
                self._checkpoint("terminal")
                return result
        result.stop_reason = "action_budget"
        for index in range(1, self.max_actions + 1):
            if time.monotonic() - started >= self.max_seconds:
                result.stop_reason = "time_budget"
                break
            before_text = driver.visible_text()
            before_img = self._screenshot(driver)
            self._capture_runtime(driver, "background", state=state)
            ctx = builder.build(pm, state, CtxObservation(screenshot=before_img, visible_text=before_text),
                                result.steps)
            candidates = planner.extract_candidates(driver)
            coverage = driver.interaction_coverage() if hasattr(driver, "interaction_coverage") else {}
            input_diagnostics = getattr(planner, "input_diagnostics", [])
            if input_diagnostics:
                coverage["input_constraints"] = deepcopy(input_diagnostics)
            warnings = []
            if input_diagnostics:
                warnings.append(tr("部分输入约束无法构造合法样本，相关提交路径未验证"))
            if coverage.get("truncated"):
                warnings.append(tr("可交互控件枚举已截断，剩余区域未检查"))
            if coverage.get("frames"):
                warnings.append(tr("frame 内容未访问，不计为已覆盖"))
            if coverage.get("shadow", {}).get("open_roots"):
                warnings.append(tr("shadow 内容的枚举、状态与回放尚未验证"))
            if coverage.get("ambiguous_modal"):
                warnings.append(tr("多个可见 modal 无法确定活动层，未继续操作"))
            if coverage.get("detached_or_skipped"):
                warnings.append(tr("部分控件已消失或无法读取，覆盖不完整"))
            for warning in warnings:
                if warning not in coverage_warnings:
                    self._diagnostic("interaction_coverage", warning)
                    coverage_warnings.add(warning)
            if result.scope is not None:
                candidates = [c for c in candidates if result.scope.matches(c)]
            action = planner.plan(ctx, candidates, tracker.graph())
            if action is None:
                result.stop_reason = "no_candidates"
                if coverage.get("modal_active") and coverage.get("enumerated") == 0:
                    self._diagnostic("interaction_coverage", tr("可见 modal 中没有可识别的操作控件，未继续操作背景"))
                if not result.steps:
                    self._diagnostic("exploration", tr("未执行任何可交互动作，无法判断交互质量"))
                break
            before_state = state
            action_key = (state.id, json.dumps(asdict(action), sort_keys=True, ensure_ascii=False))
            identity = action_attempts.setdefault(action_key, [f"A-{len(action_attempts) + 1:05d}", 0])
            identity[1] += 1
            step = {"index": index, "step_id": f"ST-{index:05d}", "action_id": identity[0],
                    "attempt": identity[1], "action": asdict(action), "state_before": state.id,
                    "status": "inconclusive", "cognitive_status": "pending", "error": "",
                    "execution_status": "not_started", "evidence_ids": [], "phases": {"expectation": "started"},
                    "interaction_coverage": coverage,
                    "input": {"url": driver.url(), "visible_text": before_text[:4000], "state_id": state.id}}
            ctx.run_id, ctx.step_id, ctx.action_id = result.run_id, step["step_id"], step["action_id"]
            page_info = PageInfo(route=driver.url(), elements=_describe_candidates(candidates))
            if hasattr(exp_engine, "prepare_input"):
                step["input"]["cognitive"] = exp_engine.prepare_input(ctx, page_info, action)
                def save_generation(data):
                    step["expectation_generation"] = deepcopy(data)
                    self._checkpoint("expectation")
                exp_engine.roles.on_generation = save_generation
            result.steps.append(step)
            if before_img:
                before_path = self._writer.directory / "steps" / step["step_id"] / "before.png"
                atomic_write_bytes(before_path, before_img)
                step["input"]["screenshot"] = str(before_path.resolve())
            self._checkpoint("expectation")
            expectations = []
            try:
                expectations = exp_engine.expect(ctx, page_info, action=action)
                step["expectations"] = [asdict(e) if is_dataclass(e) else {"text": str(e)} for e in expectations]
                if not expectations:
                    raise JudgmentError(tr("未形成可检查的事前预期，认知检查未完成"), status="inconclusive")
                if not all(valid_basis(getattr(e, "expectation_basis", None)) for e in expectations):
                    raise ValueError(tr("事前预期缺少有效依据，认知检查未完成"))
                step["phases"]["expectation"] = "completed"
            except StorageError:
                raise
            except JudgmentError as exc:
                step.update(status=exc.status, cognitive_status=exc.status, error=exc.error)
                step["phases"]["expectation"] = exc.status
            except Exception as exc:
                step.update(status="failed", cognitive_status="failed", error=tr("预期生成失败：{error}", error=exc))
                step["phases"]["expectation"] = "failed"
            finally:
                if hasattr(exp_engine, "last_generation"):
                    step["expectation_generation"] = deepcopy(exp_engine.last_generation)
            self._checkpoint("expectation")
            if time.monotonic() >= deadline:
                step.update(status="inconclusive", cognitive_status="inconclusive", error=tr("动作前运行时间预算耗尽"))
                step["phases"]["action"] = "not_started"
                result.stop_reason = "time_budget"
                break
            self._capture_runtime(driver, "background", state=state)
            self._runtime_context(driver, "action", step)
            step["execution_status"] = "started"
            step["phases"]["action"] = "started"
            self._checkpoint("action")
            if hasattr(driver, "on_execution"):
                def save_execution(data):
                    step["execution"] = data
                    self._checkpoint("action")
                driver.on_execution = save_execution
            try:
                execution = driver.execute(action, timeout=3000)
                if isinstance(execution, dict):
                    step["execution"] = deepcopy(execution)
                    if execution.get("status") in {"input_rejected", "input_unverified"}:
                        raise RuntimeError(tr("填值未被控件接受或无法验证，未将后续提交视为成功"))
                step["execution_status"] = "completed"
                step["phases"]["action"] = "completed"
                planner.record_result(action, before_state.id, True)
                if isinstance(execution, dict) and execution.get("wait", {}).get("status") in {"timeout", "failed"}:
                    step.update(status="inconclusive", cognitive_status="inconclusive",
                                error=tr("动作已发出，观察窗口未稳定或读取失败，认知结果未判断"))
            except StorageError:
                raise
            except Exception as exc:
                step.update(status="action_failed", cognitive_status="inconclusive", error=str(exc),
                            execution_status="failed")
                step["phases"]["action"] = "failed"
                planner.record_result(action, before_state.id, False)
                execution = getattr(driver, "last_execution", {})
                if "emitted" in execution and execution["emitted"] is None and hasattr(planner, "record_uncertain"):
                    planner.record_uncertain(action, before_state.id)
            finally:
                if hasattr(driver, "on_execution"):
                    driver.on_execution = None
                if isinstance(getattr(driver, "last_execution", None), dict):
                    step["execution"] = deepcopy(driver.last_execution)
                step["phases"]["raw_capture"] = "started"
                runtime, technical = self._capture_runtime(driver, "action", action, step, before_state)
                step["phases"]["raw_capture"] = "completed" if runtime is not None else "failed"
                self._runtime_context(driver, "background")
            # Raw facts and candidates are committed before another screenshot,
            # state read or model request can block/fail.
            after_img = self._screenshot(driver, step)
            try:
                after_text = driver.visible_text()
                state = tracker.observe(driver.url(), after_text,
                                        action if step["execution_status"] == "completed" else None,
                                        form_state=getattr(driver, "form_state", lambda: None)(), step_id=step["step_id"])
                step["state_after"] = state.id
                step["visible_result"] = after_text[:4000]
            except Exception as exc:
                self._diagnostic("state", exc, step)
                step.update(status="inconclusive", cognitive_status="inconclusive", error=str(exc))
            result.states = tracker.sequence()
            tracker.record_attempt(action, before_state, state, step_id=step["step_id"],
                                   status=step["execution_status"], execution=step.get("execution"), error=step["error"])
            step["trajectory"] = tracker.attempts()[-1]
            raw_observation = Observation(before_image=before_img, after_image=after_img,
                                          runtime=runtime or RuntimeObservation())
            if after_img:
                path = self._writer.directory / "steps" / step["step_id"] / "after.png"
                atomic_write_bytes(path, after_img)
                step["after_screenshot"] = str(path.resolve())
            for evidence in technical:
                self._evidence.attach_observation(evidence, raw_observation, before_state, state)
                self._persist_evidence(evidence)
            self._checkpoint("raw_capture")
            if step["cognitive_status"] != "pending" or step["execution_status"] != "completed":
                continue
            if before_img is None or after_img is None or runtime is None:
                step.update(status="inconclusive", cognitive_status="inconclusive", error=tr("观察材料缺失"))
                self._checkpoint("raw_capture")
                continue
            step["phases"]["visual"] = "started"
            self._checkpoint("visual")
            try:
                observation = obs_engine.observe_visual(before_img, after_img, action, driver, runtime)
                observation.run_id, observation.step_id, observation.action_id = result.run_id, step["step_id"], step["action_id"]
                observation.before_text = ctx.visible_text
                observation.after_text = builder.build(None, state, CtxObservation(visible_text=step.get("visible_result", "")), []).visible_text
                observation.control_state = deepcopy(step.get("execution", {}).get("focus_observation", {}))
                step["visual_observation"] = asdict(observation.visual)
                step["phases"]["visual"] = "completed"
            except Exception as exc:
                step.update(status="observation_failed", cognitive_status="failed", error=str(exc))
                step["phases"]["visual"] = "failed"
                self._checkpoint("visual")
                continue
            step["phases"]["judgment"] = "started"
            if hasattr(exp_engine, "on_judgment"):
                def save_judgment(data):
                    step["judgment_outputs"] = deepcopy(data)
                    self._checkpoint("judgment")
                exp_engine.on_judgment = save_judgment
            self._checkpoint("judgment")
            try:
                judgment = exp_engine.evaluate(expectations, observation)
                step["judgment_result"] = {"status": judgment.status, "error": judgment.error,
                                          "unverifiable_expectation_ids": getattr(judgment, "unverifiable_expectation_ids", [])}
                step.update(status=judgment.status, cognitive_status=judgment.status, error=judgment.error)
                if step.get("expectation_generation", {}).get("coverage") == "partial":
                    if judgment.status == "passed":
                        step.update(status="inconclusive", cognitive_status="inconclusive",
                                    error=tr("已检查要求满足，但仍有采样要求未决，认知检查不完整"))
                    elif judgment.status == "mismatch":
                        step["error"] = tr("已检查要求存在落差，另有采样要求未决，认知检查不完整")
                step["phases"]["judgment"] = judgment.status
                evs = self._evidence.build(judgment.mismatches, observation, action, state, driver,
                                           before_state=before_state, run_id=result.run_id,
                                           step_id=step["step_id"], action_id=step["action_id"],
                                           expectations=expectations)
                for evidence in evs:
                    self._persist_evidence(evidence)
                result.evidences.extend(evs)
                step["evidence_ids"].extend(e.id for e in evs)
            except StorageError:
                raise
            except Exception as exc:
                step.update(status="failed", cognitive_status="failed", error=str(exc))
                step["phases"]["judgment"] = "failed"
            finally:
                if hasattr(exp_engine, "last_judgment"):
                    step["judgment_outputs"] = deepcopy(exp_engine.last_judgment)
            self._checkpoint("judgment")
        self._capture_runtime(driver, "background", state=state)
        try:
            # Optional grouping cannot mutate a half-computed live set.
            saved = load_snapshot(self._writer.directory)
            candidates = [Evidence.from_dict(row) for row in saved["evidences"]]
            issues = Deduplicator().cluster(candidates)
            assignments = {e.id: e.issue_id for e in candidates}
            for evidence in result.evidences:
                evidence.issue_id = assignments[evidence.id]
            result.issues = issues
            self._checkpoint("grouping")
            for evidence in result.evidences:
                self._persist_evidence(evidence)
        except StorageError:
            raise
        except Exception as exc:
            self._diagnostic("dedup", exc)
        self._checkpoint("investigation")
        agent = InvestigationAgent(self.client)
        for issue in result.issues:
            self._checkpoint("investigation")
            try:
                investigation = agent.investigate_issue(project, issue, result.evidences, driver)
                result.investigations.append(investigation)
                if investigation.status == "failed":
                    self._diagnostic("investigation", investigation.error)
            except Exception as exc:
                result.investigations.append(Investigation(issue_id=issue.id, evidence_ids=list(issue.evidence_ids),
                                                           status="failed", error=str(exc)))
                self._diagnostic("investigation", exc)
            self._checkpoint("investigation")
        self._checkpoint("terminal")
        return result

    def _screenshot(self, driver, step=None):
        try:
            return driver.screenshot()
        except Exception as exc:
            self._diagnostic("artifact", f"artifact_missing: {exc}", step)
            return None


def _describe_candidates(candidates) -> list:
    out = []
    for c in candidates:
        tag = (c.tag or "").strip()
        text = (c.text or "").strip()
        label = f"{tag}「{text}」" if tag and text else (text or tag)
        if label:
            out.append(label)
    return out


def _action_label(action) -> str:
    t = getattr(action, "type", "") or ""
    target = getattr(action, "target", None)
    label = ""
    if target is not None:
        label = getattr(target, "text", "") or getattr(target, "selector", "") or ""
    return " ".join(x for x in (str(t), str(label)) if x).strip() or str(action)
