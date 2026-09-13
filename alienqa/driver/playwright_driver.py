"""Playwright 实现：click/hover/type + 截图 + console/network 采集 + 回放数据。"""
from dataclasses import asdict

from .action import Action, Target
from .base import BaseDriver
from .runtime import RuntimeSignals

_DEFAULT_VIEWPORT = {"width": 1280, "height": 800}


class PlaywrightDriver(BaseDriver):
    def __init__(self, headless: bool = True, record_video_dir: str | None = None):
        self._headless = headless
        self._record_video_dir = record_video_dir
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._signals = RuntimeSignals()
        self._action_sequence: list = []

    # ---- 生命周期 ----

    def launch(self, url: str) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context(
            viewport=_DEFAULT_VIEWPORT,
            record_video_dir=self._record_video_dir,
        )
        self._page = self._context.new_page()
        self._attach_listeners()
        self._page.goto(url)
        self.wait_for_settle()

    @classmethod
    def from_project(cls, project, headless: bool = True, record_video_dir: str | None = None):
        """直接消费 Project.base_url 启动（与 Loader 打通）。"""
        d = cls(headless=headless, record_video_dir=record_video_dir)
        d.launch(project.base_url)
        return d

    def navigate(self, url: str) -> None:
        self._page.goto(url)
        self.wait_for_settle()

    def close(self) -> None:
        if self._context is not None:
            self._context.close()  # flush 视频
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()

    # ---- 信号采集 ----

    def _attach_listeners(self) -> None:
        self._page.on("console", self._on_console)
        self._page.on("pageerror", lambda exc: self._signals.page_errors.append(str(exc)))
        self._page.on("requestfailed", self._on_request_failed)
        self._page.on("response", self._on_response)

    def _on_console(self, msg) -> None:
        if msg.type == "error":
            self._signals.console_errors.append(msg.text)

    def _on_request_failed(self, req) -> None:
        self._signals.network_failures.append(f"{req.method} {req.url} -> {req.failure}")

    def _on_response(self, resp) -> None:
        if resp.status >= 400:
            self._signals.http_errors.append(f"{resp.request.method} {resp.url} -> {resp.status}")

    # ---- 执行 ----

    def execute(self, action: Action, timeout: int = 3000) -> None:
        self._action_sequence.append(action)
        last_error = None
        for _name, get_locator in self._locator_chain(action.target):
            try:
                self._perform(action, get_locator(), timeout)
                self.wait_for_settle()
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if action.target.x is not None and action.target.y is not None:
            self._perform_at_coords(action, action.target.x, action.target.y)
            self.wait_for_settle()
            return
        raise RuntimeError(f"action 执行失败 {action}: {last_error}")

    def _locator_chain(self, target: Target):
        """定位优先级：text → role → selector（坐标兜底在 execute 中处理）。"""
        chain = []
        if target.text:
            chain.append(("text", lambda: self._page.get_by_text(target.text, exact=False)))
        if target.role:
            chain.append(("role", lambda: self._page.get_by_role(target.role)))
        if target.selector:
            chain.append(("selector", lambda: self._page.locator(target.selector)))
        if not chain:
            raise ValueError("target 至少需要 text / role / selector 之一")
        return chain

    def _perform(self, action: Action, locator, timeout: int) -> None:
        if action.type == "click":
            locator.click(timeout=timeout)
        elif action.type == "hover":
            locator.hover(timeout=timeout)
        elif action.type == "type":
            locator.fill(action.text, timeout=timeout)
        elif action.type == "press":
            locator.press(action.text, timeout=timeout)
        else:
            raise ValueError(f"未知 action 类型: {action.type}")

    def _perform_at_coords(self, action: Action, x: int, y: int) -> None:
        if action.type == "click":
            self._page.mouse.click(x, y)
        elif action.type == "hover":
            self._page.mouse.move(x, y)
        else:
            raise ValueError(f"坐标兜底不支持 action 类型: {action.type}")

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
        return self._page.url

    def visible_text(self) -> str:
        return self._page.locator("body").inner_text()

    def interactive_elements(self) -> list:
        """枚举当前页面可交互元素（候选动作来源）。"""
        sel = "button, a[href], input, select, textarea, [role='button'], [role='link']"
        items = []
        locator = self._page.locator(sel)
        for i in range(locator.count()):
            loc = locator.nth(i)
            try:
                visible = loc.is_visible()
            except Exception:
                continue
            try:
                text = (loc.inner_text() or "").strip()
            except Exception:
                text = ""
            try:
                tag = loc.evaluate("el => el.tagName.toLowerCase()")
            except Exception:
                tag = ""
            try:
                href = loc.get_attribute("href") or ""
                role = loc.get_attribute("role") or ""
            except Exception:
                href, role = "", ""
            items.append({
                "selector": self._stable_selector(loc),
                "text": text,
                "tag": tag,
                "href": href,
                "role": role,
                "visible": visible,
            })
        return items

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
        return RuntimeSignals(
            console_errors=list(self._signals.console_errors),
            page_errors=list(self._signals.page_errors),
            network_failures=list(self._signals.network_failures),
            http_errors=list(self._signals.http_errors),
        )

    def clear_runtime(self) -> None:
        """清空运行时信号累积（每次动作前调用，采集单动作增量）。"""
        self._signals = RuntimeSignals()

    def replay_data(self) -> dict:
        """回放所需的完整上下文（为 Replay Engine 铺路）。"""
        return {
            "browser": self._browser.version if self._browser else "unknown",
            "viewport": dict(_DEFAULT_VIEWPORT),
            "url": self._page.url if self._page else "",
            "action_sequence": [asdict(a) for a in self._action_sequence],
        }

    def wait_for_settle(self) -> None:
        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass
        self._page.wait_for_timeout(300)
