"""Observation Engine 测试：运行时增量、http_status、白屏分、视觉解析、合并（mock LLM）。"""
import io
from types import SimpleNamespace

from PIL import Image

from alienqa.driver import Action, RuntimeSignals, Target
from alienqa.llm import LLMClient, LLMConfig, RoleConfig
from alienqa.observation import (
    Observation,
    ObservationEngine,
    RuntimeObservation,
    RuntimeObserver,
    VisualObserver,
    blank_screen_score,
)
from alienqa.observation.runtime_observer import _parse_http_status


class _FakeLiteLLM:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = []

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        item = self.texts.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=item))],
            model=kwargs["model"],
            usage=None,
        )


class _FakePage:
    def __init__(self, signals, url="/orders"):
        self._signals = signals
        self._url = url

    def collect_runtime(self):
        return self._signals

    def url(self):
        return self._url


def _png(white=True):
    im = Image.new("L", (64, 64), 255 if white else 0)
    if not white:
        im.putdata([(i * 7) % 256 for i in range(64 * 64)])
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _visual_engine(monkeypatch, texts):
    fake = _FakeLiteLLM(texts)
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: fake)
    cfg = LLMConfig(roles={"visual": RoleConfig(model="gpt-4o", temperature=0.1)})
    return ObservationEngine(LLMClient(cfg)), fake


# ---- 运行时观察 ----

def test_runtime_observer_delta():
    before = RuntimeSignals(console_errors=["old"], page_errors=["old"])
    after = RuntimeSignals(
        console_errors=["old", "new"],
        page_errors=["old"],
        network_failures=["nf"],
        http_errors=["GET http://h/api -> 500"],
    )
    page = _FakePage(after, url="/orders")
    ro = RuntimeObserver().observe(page, before=before)
    assert ro.console_errors == ["new"]
    assert ro.js_exceptions == []
    assert ro.network_failures == ["nf"]
    assert ro.http_status == {"/api": 500}
    assert ro.url == "/orders"


def test_http_status_parsing():
    out = _parse_http_status([
        "GET http://127.0.0.1:8000/api/refund -> 500",
        "POST http://h/order -> 404",
    ])
    assert out == {"/api/refund": 500, "/order": 404}


# ---- 白屏分 ----

def test_blank_screen_score_white_and_noisy():
    assert blank_screen_score(_png(white=True)) > 0.9
    assert blank_screen_score(_png(white=False)) < 0.2


def test_blank_screen_score_invalid_image():
    assert blank_screen_score(b"not-an-image") == 0.0


def test_blank_screen_score_with_visible_text():
    """白底正常页（有可见文字）不应被判定为白屏。"""
    white = _png(white=True)
    assert blank_screen_score(white) > 0.9
    assert blank_screen_score(white, visible_text="有内容") == 0.0


# ---- 视觉观察 ----

def test_visual_observer_parses_llm(monkeypatch):
    fake = _FakeLiteLLM(['{"changes": ["text_changed", "modal_opened"], "summary": "弹窗出现"}'])
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: fake)
    cfg = LLMConfig(roles={"visual": RoleConfig(model="gpt-4o", temperature=0.1)})
    vo = VisualObserver(LLMClient(cfg)).observe(b"before", b"after", "click 保存")
    assert vo.changes == ["text_changed", "modal_opened"]
    assert vo.summary == "弹窗出现"
    assert 0.0 <= vo.blank_screen_score <= 1.0


# ---- 合并 Observation ----

def test_observation_technical_flattens():
    obs = Observation(
        runtime=RuntimeObservation(console_errors=["e1"], http_status={"/api": 500}, url="/orders")
    )
    t = obs.technical
    assert t["console_errors"] == ["e1"]
    assert t["http_status"] == {"/api": 500}
    assert t["url"] == "/orders"


def test_observation_engine_end_to_end(monkeypatch):
    engine, _ = _visual_engine(monkeypatch, ['{"changes": ["text_changed"], "summary": "文字变了"}'])
    page = _FakePage(RuntimeSignals(
        console_errors=["e"],
        http_errors=["GET http://h/api/x -> 500"],
    ))
    obs = engine.observe(b"before", b"after", Action("click", Target(text="保存")), page)
    assert obs.before_image == b"before"
    assert obs.after_image == b"after"
    assert obs.action_desc == "click 保存"
    assert obs.visual.changes == ["text_changed"]
    assert obs.runtime.console_errors == ["e"]
    assert obs.runtime.http_status == {"/api/x": 500}


def test_observation_duck_types_for_08():
    obs = Observation(before_image=b"a", after_image=b"b", action_desc="click")
    assert obs.before_image == b"a"
    assert obs.after_image == b"b"
    assert obs.action_desc == "click"
    assert isinstance(obs.technical, dict)
