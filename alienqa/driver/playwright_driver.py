"""Playwright 实现：click/hover/type + 截图 + console/network 采集 + 回放数据。"""
from ..i18n import t
from dataclasses import asdict
from copy import deepcopy
import time

from .browser_dom import INTERACTIVE, METADATA, FORM_STATE, SETTLE_STATE, COVERAGE, SURFACES, FOCUS

from .action import Action, Target
from .base import BaseDriver
from .runtime import RuntimeSignals

_DEFAULT_VIEWPORT = {"width": 1280, "height": 800}
_MAX_INTERACTIVE = 200  # 交互元素枚举上限，防止巨型 DOM（如 swagger）枚举到卡死


class PlaywrightDriver(BaseDriver):
    def __init__(self, headless: bool = True, record_video_dir: str | None = None,
                 browser: str = "chrome", viewport: dict | None = None):
        self._headless = headless
        self._record_video_dir = record_video_dir
        self._browser_name = browser  # "chrome"（默认，系统 Google Chrome）或 "chromium"（Playwright 自带）
        self._viewport = dict(viewport or _DEFAULT_VIEWPORT)
        self._deadline = None
        self._execution_deadline = None
        self.last_execution = {}
        self.last_wait = {}
        self._attempts = []
        self._coverage = {}
        self._popup_origins = {}
        self.on_execution = None
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._signals = RuntimeSignals()
        self._action_sequence: list = []
        self._initial_url = ""
        self._initial_storage_state: dict = {"cookies": [], "origins": []}

    # ---- 生命周期 ----

    def launch(self, url: str, storage_state: str | dict | None = None) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._launch_browser()
        kwargs = {"viewport": self._viewport}
        if self._record_video_dir:
            kwargs["record_video_dir"] = self._record_video_dir
        if storage_state:
            kwargs["storage_state"] = storage_state
        self._context = self._browser.new_context(**kwargs)
        self._page = self._context.new_page()
        self._attach_listeners()
        self._initial_url = url
        self._initial_storage_state = deepcopy(self.storage_state())
        self._page.goto(url, wait_until="domcontentloaded", timeout=10000)
        self.wait_for_settle()
        self.access_result = {"requested_url": url, "actual_url": self._page.url,
                              "redirected": url != self._page.url,
                              "session_storage": "not_restored", "authentication": "unverified"}
        self._initial_storage_state = deepcopy(self.storage_state())
        self._action_sequence = []
        self._popup_origins = {}

    def _launch_browser(self):
        """默认优先系统 Chrome（channel='chrome'）；不可用时回退 Playwright 自带 Chromium。"""
        if self._browser_name == "chromium":
            self._actual_browser = "chromium"
            return self._pw.chromium.launch(headless=self._headless)
        try:
            self._actual_browser = "chrome"
            return self._pw.chromium.launch(headless=self._headless, channel="chrome")
        except Exception:
            self._actual_browser = "chromium"
            return self._pw.chromium.launch(headless=self._headless)

    @classmethod
    def from_project(cls, project, headless: bool = True, record_video_dir: str | None = None,
                     browser: str = "chrome"):
        """直接消费 Project.base_url 启动（与 Loader 打通）。"""
        d = cls(headless=headless, record_video_dir=record_video_dir, browser=browser)
        d.launch(project.base_url)
        return d

    def navigate(self, url: str) -> None:
        self._page.goto(url, wait_until="domcontentloaded", timeout=10000)
        self.wait_for_settle()

    def close(self) -> None:
        first_error = None
        for attr, method in (("_context", "close"), ("_browser", "close"), ("_pw", "stop")):
            resource = getattr(self, attr)
            if resource is not None:
                try:
                    getattr(resource, method)()
                except Exception as exc:
                    first_error = first_error or exc
                finally:
                    setattr(self, attr, None)
        self._page = None
        if first_error:
            raise first_error

    # ---- 信号采集 ----

    def _attach_listeners(self) -> None:
        self._page.on("console", self._on_console)
        self._page.on("pageerror", lambda exc: self._signals.record("page_error", {"message": str(exc)}))
        self._page.on("requestfailed", self._on_request_failed)
        self._page.on("response", self._on_response)

    def _on_console(self, msg) -> None:
        if msg.type == "error":
            self._signals.record("console_error", {"message": msg.text})

    def _on_request_failed(self, req) -> None:
        self._signals.record("request_failed", {"method": req.method, "url": req.url,
                                                "message": str(req.failure), "resource_type": req.resource_type})

    def _on_response(self, resp) -> None:
        self._signals.record("http_response", {"method": resp.request.method, "url": resp.url,
                                               "status": resp.status, "resource_type": resp.request.resource_type})

    def set_runtime_context(self, run_id: str, step_id=None, action_id=None, phase="entry") -> None:
        self._signals.run_id = run_id
        self._signals.step_id = step_id
        self._signals.action_id = action_id
        self._signals.phase = phase

    # ---- 执行 ----

    def set_deadline(self, deadline: float | None) -> None:
        """Absolute monotonic run deadline, shared by locator/action/observation."""
        self._deadline = deadline

    def _remaining_ms(self) -> int:
        deadlines = [d for d in (self._deadline, self._execution_deadline) if d is not None]
        return max(0, int((min(deadlines) - time.monotonic()) * 1000)) if deadlines else 3000

    def _publish_execution(self):
        if self.on_execution:
            self.on_execution(deepcopy(self.last_execution))

    def execute(self, action: Action, timeout: int = 3000) -> dict:
        started = time.monotonic()
        self._execution_deadline = started + timeout / 1000
        result = {"step_id": self._signals.step_id, "action_id": self._signals.action_id,
                  "status": "started", "emitted": False, "attempts": [], "locator": {},
                  "wait": {"status": "not_started"}, "url_before": self.url(), "url_after": self.url()}
        self.last_execution = result
        recorded = False
        old_surfaces = self._surfaces()
        result["focus_observation"] = {"before": {"status": "unavailable"}, "after": {"status": "unavailable"},
            "observation_ref": f"scan.json#steps/{result['step_id']}/execution/focus_observation"}
        try:
            if self._remaining_ms() <= 0:
                raise RuntimeError("action budget exhausted")
            last_error = "target_not_found"
            for strategy, get_locator in self._locator_chain(action.target):
                if self._remaining_ms() <= 0:
                    raise RuntimeError("action budget exhausted")
                attempt = {"strategy": strategy, "matches": 0, "status": "not_found"}
                result["attempts"].append(attempt)
                try:
                    loc = get_locator()
                    # Do not silently choose a first match. Only visible targets qualify.
                    count = loc.count()
                    if isinstance(count, int):
                        loc = loc.filter(visible=True)
                        count = loc.count()
                        attempt["matches"] = count
                        if count > 1:
                            if strategy == "selector" and (action.target.name or action.target.label):
                                attempt["status"] = "ambiguous_selector"
                                continue
                            raise RuntimeError("ambiguous_target")
                        if count == 0:
                            continue
                        if strategy == "selector" and (action.target.name or action.target.label):
                            metadata = loc.evaluate(METADATA, timeout=max(1, self._remaining_ms()))
                            expected = action.target.name or action.target.label
                            if metadata["name"] != expected or (action.target.role and metadata["role"] != action.target.role):
                                attempt["status"] = "semantic_mismatch"
                                continue
                    # count non-integer is only for legacy test doubles.
                    attempt["status"] = "located"
                    result["locator"] = {"strategy": strategy, "scope": action.target.scope,
                                         "selector": action.target.selector if strategy == "selector" else None}
                    # Reserve some remaining time for semantic fallbacks.
                    action_ms = self._remaining_ms()
                    if strategy == "selector" and (action.target.name or action.target.text or action.target.label):
                        action_ms = min(action_ms, 800)
                    if action.type == "click":
                        loc.click(trial=True, timeout=max(1, action_ms))
                    result["focus_observation"]["before"] = self._focus(loc)
                    result["emitted"] = None  # invocation may fail after dispatch
                    self._perform(action, loc, max(1, self._remaining_ms()))
                    result["emitted"] = True
                    break
                except Exception as exc:
                    attempt.update(status="failed", error=str(exc))
                    last_error = str(exc)
                    if result["emitted"] is None or "ambiguous_target" in last_error:
                        raise
            if not result["emitted"]:
                if action.target.x is None or action.target.y is None:
                    raise RuntimeError(last_error)
                if self._remaining_ms() <= 0:
                    raise RuntimeError("action budget exhausted")
                current = self._page.viewport_size
                if action.target.viewport and action.target.viewport != current:
                    raise RuntimeError("coordinate viewport differs from recorded viewport")
                result["locator"] = {"strategy": "coordinates", "viewport": current,
                                     "limitation": "position depends on recorded layout"}
                result["emitted"] = None
                self._perform_at_coords(action, action.target.x, action.target.y)
                result["emitted"] = True
            result["status"] = "completed"
            # Commit emission before waiting: a timeout must never trigger another click.
            record = asdict(deepcopy(action))
            record.update(step_id=result["step_id"], action_id=result["action_id"], locator=deepcopy(result["locator"]))
            if result["locator"]["strategy"] == "coordinates":
                record["target"]["viewport"] = result["locator"]["viewport"]
            self._action_sequence.append(record)
            recorded = True
            self._publish_execution()
            try:
                wait = self.wait_for_settle()
                result["wait"] = wait if isinstance(wait, dict) else {"status": "unrecorded"}
            except Exception as exc:
                result["wait"] = {"status": "failed", "error": str(exc)}
            if action.type in {"type", "select"}:
                try:
                    # Re-resolve after rerender instead of holding an ElementHandle.
                    actual = loc.input_value(timeout=max(1, self._remaining_ms())) if action.type == "select" or not loc.evaluate("el=>el.isContentEditable", timeout=max(1, self._remaining_ms())) else loc.inner_text(timeout=max(1, self._remaining_ms()))
                    result["value_accepted"] = actual == action.text
                    if not result["value_accepted"]:
                        result["status"] = "input_rejected"
                except Exception:
                    result["value_accepted"] = None
                    result["status"] = "input_unverified"
            if result["locator"].get("strategy") != "coordinates":
                result["focus_observation"]["after"] = self._focus(loc)
            # Only an emitted action with an unchanged URL can own newly visible surfaces.
            if result["emitted"] is True and self.url() == result["url_before"]:
                old_selectors = {s["selector"] for s in old_surfaces}
                parent_owners = self._popup_origins.get((self.url(), action.target.scope), [])
                origin = {"selector": action.target.selector or "", "text": action.target.text or action.target.name or ""}
                for surface in self._surfaces():
                    if surface["selector"] not in old_selectors:
                        self._popup_origins[(self.url(), surface["selector"])] = [origin, *parent_owners][:12]
            return result
        except Exception as exc:
            result.update(status="failed", error=str(exc))
            from alienqa.run_writer import StorageError
            if isinstance(exc, StorageError):
                raise
            raise RuntimeError(f"action execution failed: {exc}") from exc
        finally:
            result.update(url_after=self.url(), elapsed_ms=round((time.monotonic()-started)*1000))
            if recorded and result["status"] in {"input_rejected", "input_unverified"}:
                # Failed input is diagnostic, not a successful replay prefix.
                self._action_sequence.pop()
            self._attempts.append(deepcopy(result))
            self._publish_execution()
            self._execution_deadline = None

    def _locator_chain(self, target: Target):
        root = self._page
        if target.scope:
            root = self._page.locator(target.scope).filter(visible=True)
            if root.count() != 1:
                raise RuntimeError("ambiguous_target scope" if root.count() > 1 else "scope_not_found")
        chain = []
        if target.selector:
            chain.append(("selector", lambda: root.locator(target.selector)))
        if target.label:
            chain.append(("label", lambda: root.get_by_label(target.label, exact=True)))
        if target.role:
            if target.name:
                chain.append(("role_name", lambda: root.get_by_role(target.role, name=target.name, exact=True)))
            else:
                chain.append(("role", lambda: root.get_by_role(target.role)))
        if target.text:
            chain.append(("text", lambda: root.get_by_text(target.text, exact=True)))
        if not chain and (target.x is None or target.y is None):
            raise ValueError("target needs text / role / selector / coordinates")
        return chain

    def _perform(self, action: Action, locator, timeout: int) -> None:
        if action.type == "click":
            locator.click(timeout=timeout, no_wait_after=True)
        elif action.type == "hover":
            locator.hover(timeout=timeout)
        elif action.type == "type":
            locator.fill(action.text, timeout=timeout)
        elif action.type == "press":
            locator.press(action.text, timeout=timeout, no_wait_after=True)
        elif action.type == "select":
            locator.select_option(value=action.text, timeout=timeout)
        elif action.type == "blur":
            locator.blur(timeout=timeout)
        else:
            raise ValueError(t("未知 action 类型: {type}", type=action.type))

    def _perform_at_coords(self, action: Action, x: int, y: int) -> None:
        if action.type == "click":
            self._page.mouse.click(x, y)
        elif action.type == "hover":
            self._page.mouse.move(x, y)
        else:
            raise ValueError(t("坐标兜底不支持 action 类型: {type}", type=action.type))

    # ---- 读取 ----

    def screenshot(self) -> bytes:
        return self._page.screenshot()

    def text(self, selector: str) -> str:
        return self._page.locator(selector).inner_text()

    def value(self, selector: str) -> str:
        return self._page.locator(selector).input_value()

    def computed_style(self, selector: str, prop: str) -> str:
        return self._page.locator(selector).evaluate(f"el => getComputedStyle(el).{prop}")

    def url(self) -> str:
        return self._page.url if self._page is not None else ""

    def visible_text(self) -> str:
        return self._page.locator("body").inner_text()

    def dom(self, selector: str | None = None) -> str:
        """当前页面 HTML（Investigator 专用，Explorer 不可见）。

        selector 给定则只取该元素的 outerHTML（11b 黑盒裁剪问题相关子树用），
        定位失败或元素不存在时返回空串。
        """
        if self._page is None:
            return ""
        if selector:
            try:
                loc = self._page.locator(selector).first
                if loc.count() == 0:
                    return ""
                return loc.evaluate("el => el.outerHTML")
            except Exception:  # noqa: BLE001
                return ""
        return self._page.content()

    def interactive_elements(self) -> list:
        """Prioritize visible portal leaves; never click through them into the background."""
        root = self._page
        surfaces = self._surfaces()
        visible_surfaces = {s["selector"] for s in surfaces}
        self._popup_origins = {key: value for key, value in self._popup_origins.items()
                               if key[0] == self.url() and key[1] in visible_surfaces}
        # role=menu/listbox also describes persistent navigation. Only explicit open state
        # or an observed newly opened surface may exclude the rest of the page.
        inactive_surfaces = sum(not s.get("active") and (self.url(), s["selector"]) not in self._popup_origins for s in surfaces)
        surfaces = [s for s in surfaces if s.get("active") or (self.url(), s["selector"]) in self._popup_origins]
        # A leaf can be nested in DOM or linked to its parent by an ARIA trigger.
        leaves = [surface for surface in surfaces if not any(
            surface["selector"] in child["ancestors"] or any(owner.get("selector") == surface["selector"] or
                self._page.locator(surface["selector"]).locator(owner["selector"]).count() > 0
                for owner in child["owners"] if owner.get("selector"))
            for child in surfaces if child is not surface)]
        if len(leaves) > 1:
            self._coverage = {"limit": _MAX_INTERACTIVE, "truncated": False,
                              "ambiguous_modal": True, "ambiguous_surface": True, "enumerated": 0}
            return []
        surface = leaves[0] if leaves else None
        owners = []
        if surface:
            root = self._page.locator(surface["selector"])
            owners = [*surface["owners"], *self._popup_origins.get((self.url(), surface["selector"]), [])]
        locator = root.locator(INTERACTIVE).filter(visible=True)
        count = locator.count()
        items = []
        for i in range(min(count, _MAX_INTERACTIVE)):
            try:
                item = locator.nth(i).evaluate(METADATA, timeout=500)
                # Main-page structural paths do not cross shadow roots reliably.
                if locator.nth(i).evaluate("el=>el.getRootNode() !== document"):
                    continue
                item["popup_owners"] = owners
                items.append(item)
            except Exception:
                continue
        if surface and (surface["role"] in {"menu", "listbox"} or count == 0):
            # Escape is a normal keyboard probe. Its success is observed, never assumed.
            focusable = root.locator('button:not([disabled]):not([aria-disabled="true"]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]').filter(visible=True)
            dismiss_target = focusable.first if focusable.count() else root
            dismiss = dismiss_target.evaluate(METADATA, timeout=500)
            dismiss.update(dismiss_surface=True, popup_owners=owners)
            items.append(dismiss)
        self._coverage = {"limit": _MAX_INTERACTIVE, "total_visible": count,
                          "persistent_surfaces": inactive_surfaces,
                          "enumerated": len(items), "truncated": count > _MAX_INTERACTIVE,
                          "modal_active": bool(surface), "active_surface": surface,
                          "detached_or_skipped": max(0, min(count, _MAX_INTERACTIVE)-len(items))}
        return items

    def _surfaces(self):
        try:
            surfaces = self._page.evaluate(SURFACES) if self._page else []
            return surfaces if isinstance(surfaces, list) else []
        except Exception:
            return []

    def _focus(self, locator):
        try:
            if locator.count() != 1:
                return {"status": "target_absent_or_ambiguous"}
            return {"status": "observed", **locator.evaluate(FOCUS, timeout=max(1, self._remaining_ms()))}
        except Exception:
            return {"status": "unavailable"}

    def interaction_coverage(self) -> dict:
        coverage = self._page.evaluate(COVERAGE) if self._page else {}
        return {**deepcopy(self._coverage), **coverage,
                "session_storage": "not_restored", "indexed_db": "not_restored",
                "canvas_drag": "unverified", "hydration": "visible_readiness_only"}

    def form_state(self) -> list:
        """Stable visible fields and ARIA state; values only feed the private digest."""
        if self._page is None:
            return []
        return self._page.locator("input,textarea,select,[contenteditable='true'],[aria-expanded],[aria-selected],[aria-checked],[aria-busy],button,[role='dialog'],dialog[open]").evaluate_all(FORM_STATE)

    def _stable_selector(self, loc) -> str:
        """尽量返回稳定唯一的选择器（id > data-* > 空）。"""
        try:
            el_id = loc.get_attribute("id")
            if el_id:
                return f"#{el_id}"
            for attr in ("data-testid", "data-view", "name"):
                val = loc.get_attribute(attr)
                if val:
                    return f"[{attr}='{val}']"
        except Exception:
            pass
        return ""

    def collect_runtime(self) -> RuntimeSignals:
        return self._signals

    def snapshot_runtime(self) -> RuntimeSignals:
        """当前运行时信号的快照（用于 per-action 增量 diff）。"""
        return deepcopy(self._signals)

    def clear_runtime(self) -> None:
        """清空运行时信号累积（每次动作前调用，采集单动作增量）。"""
        self._signals.clear()

    def storage_state(self) -> dict:
        """会话态（cookies/localStorage），供 Replay 还原。"""
        if self._context is None:
            return {}
        return self._context.storage_state()

    def replay_data(self) -> dict:
        """回放所需的完整上下文（为 Replay Engine 铺路）。"""
        return {
            "browser": self._browser.version if self._browser else "unknown",
            "browser_kind": getattr(self, "_actual_browser", self._browser_name),
            "viewport": dict(self._viewport),
            "url": self._initial_url,
            "final_url": self._page.url if self._page else "",
            "storage_state": deepcopy(self._initial_storage_state),
            "action_sequence": deepcopy(self._action_sequence),
            "attempts": deepcopy(self._attempts),
            "prefix_complete": not any(a.get("emitted") is None for a in self._attempts),
            "access_result": deepcopy(getattr(self, "access_result", {})),
            "limitations": {"session_storage": "not_restored", "indexed_db": "not_restored",
                            "automatic_login": "unsupported", "frames": "unvisited", "shadow": "unverified"},
        }

    def wait_for_settle(self) -> dict:
        """Bounded DOM/URL stability, not networkidle or framework-private hydration."""
        started = time.monotonic()
        deadline = started + min(1500, self._remaining_ms()) / 1000
        previous = None
        changed_at = started
        first = None
        last = {}
        while time.monotonic() < deadline:
            try:
                observed = self._page.evaluate(SETTLE_STATE)
            except Exception:
                # Document replacement during navigation is transient, not a second action.
                self._page.wait_for_timeout(min(50, max(1, int((deadline-time.monotonic())*1000))))
                continue
            if first is None:
                first = {"url": observed["url"], "pending": observed["pending"],
                         "visible_text": observed["text"][:4000], "text_truncated": len(observed["text"]) > 4000}
            if observed != previous:
                changed_at = time.monotonic()
                previous = observed
            last = observed
            if not observed["pending"] and time.monotonic()-started >= .6 and time.monotonic()-changed_at >= .2:
                status = "settled"
                break
            self._page.wait_for_timeout(min(50, max(1, int((deadline-time.monotonic())*1000))))
        else:
            status = "timeout"
        result = {"status": status, "pending": last.get("pending"), "initial": first,
                  "final": {"url": last.get("url", self.url()), "pending": last.get("pending"),
                            "visible_text": last.get("text", "")[:4000], "text_truncated": len(last.get("text", "")) > 4000},
                  "elapsed_ms": round((time.monotonic()-started)*1000),
                  "observation_limit_ms": round((deadline-started)*1000),
                  "limitation": "visible stability is not proof of hydration or completion of future feedback"}
        if self._signals.step_id:
            for phase in ("initial", "final"):
                if result.get(phase):
                    result[phase]["observation_ref"] = f"scan.json#steps/{self._signals.step_id}/execution/wait/{phase}"
        self.last_wait = result
        return result
