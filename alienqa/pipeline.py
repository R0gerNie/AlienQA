"""AlienQA 全链路编排器：把 01→12 串成一条流水线，产出 HTML 报告。

这是正式入口（`python -m alienqa`）背后的引擎：任何 CLI / API / 定时任务
都调用 AlienQAPipeline.run()，不再散落脚本。
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .context import ExplorationContext
from .context.models import Observation as CtxObservation
from .dedup import Deduplicator
from .driver import PlaywrightDriver
from .evidence import EvidenceEngine
from .expectation import ExpectationEngine, PageInfo
from .investigation import InvestigationAgent
from .llm import LLMClient, LLMConfig
from .loader import Project, UnitLocator, UnitScope, is_all_unit
from .mapper import ProductMapper, ProductMap
from .observation import ObservationEngine
from .planner import ActionPlanner, ExploreBudget
from .review import Decision, HumanReview, Report, ReportBuilder, ReviewState
from .state import StateTracker


def _join_focus(unit: str, instructions: str) -> str:
    parts = []
    if unit:
        parts.append(f"单元：{unit}")
    if instructions:
        parts.append(f"指令：{instructions}")
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

    @property
    def html(self) -> str:
        return self.report.html if self.report else ""


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
    """

    def __init__(
        self,
        config: LLMConfig,
        samples: int = 2,
        headless: bool = True,
        max_actions: int = 10,
        artifacts_dir: str | Path | None = None,
        auto_confirm: bool = True,
        focus: str = "",
        unit: str = "",
        instructions: str = "",
        verbose: bool = True,
    ):
        self.client = LLMClient(config)
        self.samples = samples
        self.headless = headless
        self.max_actions = max_actions
        self.artifacts_dir = artifacts_dir
        self.auto_confirm = auto_confirm
        self.unit = unit
        self.instructions = instructions
        self.focus = focus or _join_focus(unit, instructions)
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    def collect(self, project: Project) -> PipelineResult:
        """01→11：产品地图 + 探索 + 证据 + 去重 + 调查。不采信、不产报告。"""
        if getattr(project, "input_type", "") == "browser":
            return self._collect_browser(project)
        return self._collect_source(project)

    def _collect_source(self, project: Project) -> PipelineResult:
        # 02 产品地图（源码模式：先 map 后 launch）
        self._log("[02] 生成产品地图中…")
        pm = ProductMapper(self.client).map(project)
        self._log(f"[02] 主旨: {pm.brief[:160]}")
        self._log(f"[02] 功能区域: {len(pm.areas)} 个")

        # 04 浏览器
        driver = PlaywrightDriver(headless=self.headless)
        driver.launch(project.base_url)
        try:
            return self._collect_live(driver, project, pm)
        finally:
            driver.close()

    def _collect_browser(self, project: Project) -> PipelineResult:
        # 01b/02b 浏览器黑盒：先 launch 后 map（map 要读浏览器），可带登录态
        self._log("[01b] 浏览器黑盒装载（URL 模式）…")
        driver = PlaywrightDriver(headless=self.headless)
        driver.launch(project.base_url, storage_state=project.storage_state or None)
        try:
            pm = self._map_from_browser(driver, project)
            return self._collect_live(driver, project, pm)
        finally:
            driver.close()

    def _map_from_browser(self, driver, project) -> ProductMap:
        """02b：用浏览器可见文字建立产品地图（本步占位，返回空地图）。"""
        self._log("[02b] 浏览器表面产品地图待实现（02b），暂返回空 ProductMap")
        return ProductMap()

    def run(self, project: Project, output_path: str | Path | None = None) -> PipelineResult:
        """01→12：collect 之后按 auto_confirm 采信，再生成最终报告。"""
        result = self.collect(project)
        review = HumanReview(ReviewState())
        if self.auto_confirm:
            for ev in result.evidences:
                review.decide(ev.id, Decision.CONFIRMED, "CLI 自动采信")
        self._log("[12] 生成 HTML 报告中…")
        report = ReportBuilder(self.client).build(result.evidences, review.state, result.investigations)
        if output_path:
            Path(output_path).write_text(report.html, encoding="utf-8")
            self._log(f"[12] 报告已写入 {output_path}（采信 {report.accepted_count}/{report.total_count}）")
        result.report = report
        return result

    def _collect_live(self, driver, project, pm) -> PipelineResult:
        exp_engine = ExpectationEngine(self.client, samples=self.samples, focus=self.focus)
        obs_engine = ObservationEngine(self.client)
        ev_engine = EvidenceEngine(artifacts_dir=self.artifacts_dir or tempfile.mkdtemp(prefix="alienqa_"))
        planner = ActionPlanner(ExploreBudget(max_steps=self.max_actions))
        tracker = StateTracker()
        builder = ExplorationContext()

        # 05 初始状态
        state = tracker.capture(driver)
        evidences: list = []

        # 01+ 单元定位器：单元有具体语义时圈定探索范围（空/「全部」跳过，避免对空或巨型 DOM 误跑）
        scope = None
        if not is_all_unit(self.unit):
            locator = UnitLocator(self.client)
            scope = locator.locate(self.unit, self.instructions, pm.brief, driver.interactive_elements())
            self._log(f"[01+] 单元定位: {scope.summary or '未定位到具体元素（退化为全量探索）'}")
            if scope is not None and scope.summary:
                exp_engine.focus = (self.focus + f"\n定位结果：{scope.summary}").strip()

        self._log("[06] 探索启动，逐动作执行 08 预期 + 07 观察 + 09 证据…")

        for _step in range(self.max_actions):
            before_img = driver.screenshot()
            before_text = driver.visible_text()
            # 03 认知防火墙：只把白名单上下文交给陌生人
            ctx = builder.build(
                product_map=pm,
                state=state,
                observation=CtxObservation(screenshot=before_img, visible_text=before_text),
                history=tracker.sequence(),
            )
            candidates = planner.extract_candidates(driver)
            if scope is not None and not scope.is_empty():
                candidates = [c for c in candidates if scope.matches(c)]
            action = planner.plan(ctx, candidates, tracker.graph())
            if action is None:
                break

            page_info = PageInfo(route=driver.url(), elements=_describe_candidates(candidates))
            # 08 先预期（盲，不读观察结果），再执行
            expectations = exp_engine.expect(ctx, page_info)
            before_runtime = driver.snapshot_runtime()
            try:
                driver.execute(action, timeout=3000)
            except Exception as exc:  # noqa: BLE001
                self._log(f"      [skip] {_action_label(action)} 执行失败: {exc}")
                continue

            # 05 记录新状态
            state = tracker.observe(driver.url(), driver.visible_text(), action)
            after_img = driver.screenshot()

            # 07 观察：视觉(Qwen-VL) + 运行时(确定性)
            observation = obs_engine.observe(before_img, after_img, action, driver, before_runtime=before_runtime)
            self._log(
                f"      {_action_label(action)}: 视觉变化 {observation.visual.changes} "
                f"白屏分={observation.visual.blank_screen_score:.2f} "
                f"console={len(observation.runtime.console_errors)} "
                f"http={observation.runtime.http_status} net={len(observation.runtime.network_failures)}"
            )

            # 08 盲判 → 09 证据
            try:
                mismatches = exp_engine.judge(expectations, observation)
            except Exception as exc:  # noqa: BLE001
                self._log(f"      [judge 异常] {exc}")
                mismatches = []
            evs = ev_engine.build(mismatches, observation, action, state, driver)
            for ev in evs:
                ev_engine.persist(ev)
            evidences.extend(evs)
            if evs:
                self._log(f"      → 产出 {len(evs)} 条证据")

        self._log(f"[09] 共 {len(evidences)} 条证据")

        # 10 去重
        issues = Deduplicator().cluster(evidences)
        self._log(f"[10] 归并为 {len(issues)} 个 Issue")
        for issue in issues:
            self._log(f"      {issue.id} [{issue.severity.value}] {issue.title[:60]} ← {len(issue.evidence_ids)} 条证据")

        # 11 专家调查
        agent = InvestigationAgent(self.client)
        investigations = []
        self._log("[11] 专家调查中…")
        for issue in issues:
            try:
                inv = agent.investigate_issue(project, issue, evidences, driver)
                investigations.append(inv)
                self._log(f"      {issue.id}: {inv.root_cause_hypothesis[:80]}")
            except Exception as exc:  # noqa: BLE001
                self._log(f"      {issue.id} 调查失败: {exc}")

        return PipelineResult(
            report=None,
            evidences=evidences,
            issues=issues,
            investigations=investigations,
            states=tracker.sequence(),
            scope=scope,
        )


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
