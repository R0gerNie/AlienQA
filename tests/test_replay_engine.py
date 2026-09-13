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


def test_replay_signal_overlap_reproduces(tmp_path):
    fake = _FakeDriver(after_image=_png(white=True), signals=RuntimeSignals(console_errors=["TypeError"]))
    engine = ReplayEngine(replay_dir=str(tmp_path / "replay"), driver_factory=lambda: fake)
    evidence = Evidence(
        id="EV-00001",
        replay={"url": "http://x", "action_sequence": [], "cookies": [], "console": ["TypeError"], "network": []},
        artifacts={},
    )
    engine.save(evidence)
    result = engine.replay("EV-00001")
    assert result.reproduced is True  # 信号复现，即使截图不可比


def test_replay_missing_package_raises(tmp_path):
    engine = ReplayEngine(replay_dir=str(tmp_path / "replay"))
    with pytest.raises(FileNotFoundError):
        engine.replay("EV-99999")


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
