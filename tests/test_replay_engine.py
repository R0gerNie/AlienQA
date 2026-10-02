"""Replay Engine 测试：反序列化、截图相似度、会话态还原、端到端复现（mock + 真实）。"""
import io

import pytest
from PIL import Image

from alienqa.driver import Action, RuntimeSignals, Target
from alienqa.evidence import Evidence
from alienqa.replay import ReplayEngine, image_similarity


def _png(white=True):
    # 白图（255）或黑图（0）：两者像素均值差 255，用于验证相似度 [0,1]
    im = Image.new("L", (64, 64), 255 if white else 0)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class _FakeDriver:
    def __init__(self, after_image, signals=None):
        self.after_image = after_image
        self.signals = signals or RuntimeSignals()
        self.launched = {}
        self.actions = []

    def launch(self, url, storage_state=None):
        self.launched = {"url": url, "storage_state": storage_state}

    def execute(self, action, timeout=3000):
        self.actions.append(action)

    def screenshot(self):
        return self.after_image

    def collect_runtime(self):
        return self.signals

    def close(self):
        pass


# ---- S0 反序列化 ----

def test_action_target_from_dict_roundtrip():
    a = Action.from_dict({"type": "click", "target": {"text": "保存", "selector": "#save"}, "text": ""})
    assert a.type == "click"
    assert a.target.text == "保存"
    assert a.target.selector == "#save"


# ---- S5 截图相似度 ----

def test_image_similarity_same_and_diff():
    white = _png(white=True)
    noise = _png(white=False)
    assert image_similarity(white, white) > 0.99
    assert image_similarity(white, noise) < 0.2
    assert image_similarity(b"not-image", white) == 0.0


# ---- S4/S6 回放（fake driver） ----

def test_replay_reproduces_with_fake(tmp_path):
    after = _png(white=False)
    fake = _FakeDriver(after_image=after)
    engine = ReplayEngine(replay_dir=str(tmp_path / "replay"), driver_factory=lambda: fake)
    evidence = Evidence(
        id="EV-00001",
        replay={
            "url": "http://x",
            "action_sequence": [{"type": "click", "target": {"text": "保存"}}],
            "cookies": [{"name": "session"}],
            "console": [],
            "network": [],
        },
        artifacts={"after": str(tmp_path / "after.png")},
    )
    (tmp_path / "after.png").write_bytes(after)
    engine.save(evidence)
    result = engine.replay("EV-00001")
    assert result.reproduced is True
    assert result.match_score > 0.99
    # 会话态还原 + 动作重放
    assert fake.launched["url"] == "http://x"
    assert fake.launched["storage_state"] == {"cookies": [{"name": "session"}]}
    assert len(fake.actions) == 1
    assert fake.actions[0].type == "click"


def test_replay_not_reproduced_when_diff_image(tmp_path):
    fake = _FakeDriver(after_image=_png(white=False))
    engine = ReplayEngine(replay_dir=str(tmp_path / "replay"), driver_factory=lambda: fake)
    evidence = Evidence(
        id="EV-00001",
        replay={"url": "http://x", "action_sequence": [], "cookies": [], "console": [], "network": []},
        artifacts={"after": str(tmp_path / "after.png")},
    )
    (tmp_path / "after.png").write_bytes(_png(white=True))  # 原始白图，回放噪声图
    engine.save(evidence)
    result = engine.replay("EV-00001")
    assert result.reproduced is False
    assert result.note  # 降权提示


def test_replay_generic_console_error_does_not_prove_reproduction(tmp_path):
    fake = _FakeDriver(after_image=_png(white=True), signals=RuntimeSignals(console_errors=["TypeError"]))
    engine = ReplayEngine(replay_dir=str(tmp_path / "replay"), driver_factory=lambda: fake)
    evidence = Evidence(
        id="EV-00001",
        replay={"url": "http://x", "action_sequence": [], "cookies": [], "console": ["TypeError"], "network": []},
        artifacts={},
    )
    engine.save(evidence)
    result = engine.replay("EV-00001")
    assert result.reproduced is False
    assert result.status == "inconclusive"


def test_replay_restores_initial_url_and_full_storage_state(tmp_path):
    fake = _FakeDriver(after_image=_png())
    engine = ReplayEngine(tmp_path / "replay", driver_factory=lambda: fake)
    storage = {"cookies": [{"name": "session"}], "origins": [
        {"origin": "http://x", "localStorage": [{"name": "token", "value": "initial"}]},
    ]}
    engine.save(Evidence(id="EV-1", replay={
        "url": "http://x/list", "final_url": "http://x/detail",
        "storage_state": storage, "cookies": [{"name": "wrong-final"}],
        "action_sequence": [{"type": "type", "target": {"selector": "#search"}, "text": "order"}],
    }))
    result = engine.replay("EV-1")
    assert fake.launched == {"url": "http://x/list", "storage_state": storage}
    assert fake.actions[0].text == "order"
    assert "storage_state" not in str(result.to_dict())


def test_replay_action_failure_is_explicit_and_closes_driver(tmp_path):
    class Failing(_FakeDriver):
        closed = False

        def execute(self, action, timeout=3000):
            raise RuntimeError("missing #save")

        def close(self):
            self.closed = True

    fake = Failing(_png())
    engine = ReplayEngine(tmp_path / "replay", driver_factory=lambda: fake)
    engine.save(Evidence(id="EV-1", replay={"url": "http://x", "action_sequence": [
        {"type": "click", "target": {"selector": "#save"}},
    ]}))
    result = engine.replay("EV-1")
    assert result.status == "failed"
    assert "missing #save" in result.note
    assert fake.closed


def test_replay_matching_signal_from_initial_page_is_not_target_recurrence(tmp_path):
    signal = "TypeError: unrelated startup widget unavailable"
    fake = _FakeDriver(_png(), RuntimeSignals(console_errors=[signal]))
    engine = ReplayEngine(tmp_path / "replay", driver_factory=lambda: fake)
    engine.save(Evidence(id="EV-1", replay={"url": "http://x", "console": [signal],
        "action_sequence": [{"type": "click", "target": {"selector": "#save"}}]}))
    result = engine.replay("EV-1")
    assert not result.reproduced
    assert not result.matched_signals


def test_replay_missing_package_is_explicit_failure(tmp_path):
    engine = ReplayEngine(replay_dir=str(tmp_path / "replay"))
    assert engine.replay("EV-99999").status == "failed"


def test_replay_invalid_static_directory_is_explicit_failure(tmp_path):
    fake = _FakeDriver(_png())
    engine = ReplayEngine(tmp_path / "replay", driver_factory=lambda: fake)
    engine.save(Evidence(id="EV-static", replay={"url": "http://127.0.0.1:9876/index.html",
        "static_server": {"directory": str(tmp_path / "missing"), "port": 9876}}))
    result = engine.replay("EV-static")
    assert result.status == "failed"
    assert "静态" in result.note
    assert not fake.launched


def test_replay_static_port_conflict_is_explicit_failure(tmp_path, monkeypatch):
    def occupied(*args, **kwargs):
        raise OSError("Address already in use")

    monkeypatch.setattr("alienqa.replay.engine.ThreadingHTTPServer", occupied)
    engine = ReplayEngine(tmp_path / "replay", driver_factory=lambda: _FakeDriver(_png()))
    engine.save(Evidence(id="EV-static", replay={"url": "http://127.0.0.1:9876/index.html",
        "static_server": {"directory": str(tmp_path), "port": 9876}}))
    result = engine.replay("EV-static")
    assert result.status == "failed"
    assert "Address already in use" in result.note


# ---- 端到端（真实 Playwright） ----

def test_replay_end_to_end_real(http_base_url, tmp_path):
    pytest.importorskip("playwright")
    from alienqa.driver import PlaywrightDriver

    # 录制：点 #greet → after 截图
    d = PlaywrightDriver()
    d.launch(f"{http_base_url}/demo-app/index.html")
    d.execute(Action("click", Target(selector="#greet")))
    after = d.screenshot()
    replay_data = d.replay_data()
    d.close()

    after_path = tmp_path / "after.png"
    after_path.write_bytes(after)
    evidence = Evidence(
        id="EV-00042",
        replay={**replay_data, "cookies": [], "console": [], "network": []},
        artifacts={"after": str(after_path)},
    )
    engine = ReplayEngine(replay_dir=str(tmp_path / "replay"), driver_factory=PlaywrightDriver)
    engine.save(evidence)
    result = engine.replay("EV-00042")
    assert result.reproduced is True
    assert result.match_score > 0.9


def test_replay_cross_route_and_local_storage_real(http_base_url, tmp_path):
    pytest.importorskip("playwright")
    from alienqa.driver import PlaywrightDriver

    entry = f"{http_base_url}/replay-app/index.html"
    initial_storage = {"cookies": [], "origins": [{
        "origin": http_base_url,
        "localStorage": [{"name": "sessionLabel", "value": "Alice"}],
    }]}
    driver = PlaywrightDriver(browser="chromium")
    try:
        driver.launch(entry, storage_state=initial_storage)
        driver.execute(Action("click", Target(selector="#open")))
        driver.execute(Action("type", Target(selector="#message"), text="saved message"))
        driver.execute(Action("click", Target(selector="#save")))
        replay_data = driver.replay_data()
        after = driver.screenshot()
    finally:
        driver.close()
    assert replay_data["url"] == entry
    assert replay_data["final_url"].endswith("/replay-app/detail.html")
    assert replay_data["storage_state"]["origins"] == initial_storage["origins"]
    screenshot = tmp_path / "after.png"
    screenshot.write_bytes(after)
    engine = ReplayEngine(tmp_path / "replay", driver_factory=lambda: PlaywrightDriver(browser="chromium"))
    engine.save(Evidence(id="EV-route", replay=replay_data, artifacts={"after": str(screenshot)}))
    result = engine.replay("EV-route")
    assert result.status == "reproduced"
    assert result.match_score > 0.98


def test_replay_restarts_closed_static_server_real(tmp_path):
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from alienqa.driver import PlaywrightDriver

    app = tmp_path / "app"
    app.mkdir()
    (app / "index.html").write_text('<button id="save" onclick="this.textContent=\'Saved\'">Save</button>')
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(app)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    entry = f"http://127.0.0.1:{port}/index.html"
    driver = PlaywrightDriver(browser="chromium")
    try:
        driver.launch(entry)
        driver.execute(Action("click", Target(selector="#save")))
        replay_data = driver.replay_data()
        after = driver.screenshot()
    finally:
        driver.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    replay_data["static_server"] = {"directory": str(app), "port": port}
    screenshot = tmp_path / "after.png"
    screenshot.write_bytes(after)
    engine = ReplayEngine(tmp_path / "replay", driver_factory=lambda: PlaywrightDriver(browser="chromium"))
    engine.save(Evidence(id="EV-static", replay=replay_data, artifacts={"after": str(screenshot)}))
    result = engine.replay("EV-static")
    assert result.status == "reproduced"
    # Replay also releases its restored port once the browser has closed.
    probe = ThreadingHTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler)
    probe.server_close()
