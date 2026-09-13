"""模块 01 plus 单元定位器测试。"""
from types import SimpleNamespace

from alienqa.llm import LLMClient, LLMConfig, RoleConfig
from alienqa.loader import UnitLocator, UnitScope


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


class _Cand:
    def __init__(self, selector="", text="", href=""):
        self.selector = selector
        self.text = text
        self.href = href


def _locator(monkeypatch, texts):
    fake = _FakeLiteLLM(texts)
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: fake)
    cfg = LLMConfig(roles={"gist": RoleConfig(model="gpt-4o-mini", temperature=0.1)})
    return UnitLocator(LLMClient(cfg)), fake


def _elements():
    return [
        {"selector": "#name", "tag": "input", "text": "", "href": ""},
        {"selector": "#greet", "tag": "button", "text": "Greet", "href": ""},
        {"selector": "#login", "tag": "button", "text": "登录", "href": ""},
    ]


# ---- UnitScope.matches ----

def test_scope_empty_matches_all():
    assert UnitScope().matches(_Cand(text="Greet")) is True


def test_scope_selector_match():
    s = UnitScope(selectors=["#login"])
    assert s.matches(_Cand(selector="#login")) is True
    assert s.matches(_Cand(selector="#greet")) is False


def test_scope_keyword_match():
    s = UnitScope(keywords=["登录"])
    assert s.matches(_Cand(text="登录")) is True
    assert s.matches(_Cand(text="Greet")) is False
    assert UnitScope(keywords=["login"]).matches(_Cand(text="Login page")) is True


# ---- UnitLocator.locate ----

def test_locate_parses_json(monkeypatch):
    locator, fake = _locator(monkeypatch, [
        '{"selectors": ["#login"], "keywords": ["登录", "密码"], "summary": "登录表单"}',
    ])
    scope = locator.locate("登录表单", "", "某产品", _elements())
    assert scope.selectors == ["#login"]
    assert scope.keywords == ["登录", "密码"]
    assert scope.summary == "登录表单"
    assert len(fake.calls) == 1


def test_locate_falls_back_to_empty_on_bad_json(monkeypatch):
    locator, _ = _locator(monkeypatch, ["不是 JSON", "也不是 JSON"])
    scope = locator.locate("登录表单", "", "某产品", _elements())
    assert scope.is_empty()
    assert scope.unit == "登录表单"


def test_locate_skips_when_no_unit(monkeypatch):
    locator, fake = _locator(monkeypatch, [])
    scope = locator.locate("", "", "某产品", _elements())
    assert scope.is_empty()
    assert len(fake.calls) == 0
