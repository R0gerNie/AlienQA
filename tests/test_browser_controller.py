"""Browser Controller 测试：使用无数据库的轻量静态目标（HTTP 服务）。"""
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="Playwright 未安装")

from alienqa.driver import Action, PlaywrightDriver, Target
from alienqa.loader import Project

FIXTURES = Path(__file__).parent / "fixtures"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # 静默请求日志
        pass


def _wait_for(pred, timeout: float = 3.0) -> bool:
    import time as _t

    deadline = _t.time() + timeout
    while _t.time() < deadline:
        if pred():
            return True
        _t.sleep(0.1)
    return False


@pytest.fixture(scope="module")
def http_base_url():
    handler = partial(_QuietHandler, directory=str(FIXTURES))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def driver(http_base_url):
    d = PlaywrightDriver()
    d.launch(f"{http_base_url}/demo-app/index.html")
    yield d
    d.close()


# ---- 基础交互 ----

def test_click_updates_dom(driver):
    driver.execute(Action("click", Target(selector="#greet")))
    assert driver.text("#status") == "greeted"


def test_hover_triggers_shadow(driver):
    before = driver.computed_style("#card", "boxShadow")
    driver.execute(Action("hover", Target(selector="#card")))
    after = driver.computed_style("#card", "boxShadow")
    assert after != before


def test_broken_button_captures_error(driver):
    driver.execute(Action("click", Target(text="Broken")))
    signals = driver.collect_runtime()
    assert any("intentional demo error" in e for e in signals.page_errors)


def test_type_into_input(driver):
    driver.execute(Action("type", Target(selector="#name"), text="Alice"))
    assert driver.value("#name") == "Alice"


# ---- 定位降级（text → role → selector）----

def test_selector_fallback_when_text_missing(driver):
    driver.execute(Action("click", Target(text="NoSuchText", selector="#greet")), timeout=500)
    assert driver.text("#status") == "greeted"


# ---- 网络采集 ----

def test_http_error_captured(driver):
    driver.execute(Action("click", Target(selector="#fetch-404")))
    signals = driver.collect_runtime()
    assert any("404" in e for e in signals.http_errors)


def test_network_failure_captured(driver):
    driver.execute(Action("click", Target(selector="#fetch-refused")))
    assert _wait_for(lambda: any("NAME_NOT_RESOLVED" in e for e in driver.collect_runtime().network_failures))


# ---- 与 Loader 打通 ----

def test_launch_from_project(http_base_url):
    project = Project(framework="Unknown", base_url=f"{http_base_url}/demo-app/index.html")
    d = PlaywrightDriver.from_project(project)
    try:
        assert d.text("#status") == "idle"
    finally:
        d.close()


# ---- 回放数据（Replay Engine 铺路）----

def test_replay_data_captures_sequence(driver):
    driver.execute(Action("click", Target(selector="#greet")))
    data = driver.replay_data()
    assert data["browser"]
    assert data["url"].endswith("index.html")
    assert [a["type"] for a in data["action_sequence"]] == ["click"]


def test_video_recording(http_base_url, tmp_path):
    d = PlaywrightDriver(record_video_dir=str(tmp_path))
    try:
        d.launch(f"{http_base_url}/demo-app/index.html")
        d.execute(Action("click", Target(selector="#greet")))
    finally:
        d.close()
    videos = list(tmp_path.glob("*.webm"))
    assert videos
