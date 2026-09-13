"""模块 01 plus 入口文件智能识别测试。"""
from types import SimpleNamespace

from alienqa.llm import LLMClient, LLMConfig, RoleConfig
from alienqa.loader import EntryDetector, collect_entry_candidates, is_all_unit


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


def _write(tmp_path, rel, content="<html></html>"):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_collect_prefers_root_index(tmp_path):
    _write(tmp_path, "index.html")
    _write(tmp_path, "packages/app/index.html")
    _write(tmp_path, "login.html")
    cands = collect_entry_candidates(tmp_path)
    assert cands[0] == "index.html"
    assert "packages/app/index.html" in cands
    assert "login.html" in cands


def test_collect_excludes_noise_dirs(tmp_path):
    _write(tmp_path, "index.html")
    _write(tmp_path, "node_modules/foo/index.html")
    _write(tmp_path, ".git/x/index.html")
    cands = collect_entry_candidates(tmp_path)
    assert "node_modules/foo/index.html" not in cands
    assert ".git/x/index.html" not in cands


def test_detect_global_picks_best(tmp_path):
    _write(tmp_path, "app/index.html")
    assert EntryDetector().detect(tmp_path, unit="全部") == "app/index.html"


def test_detect_all_semantics_empty_and_all(tmp_path):
    _write(tmp_path, "a/index.html")
    _write(tmp_path, "b/index.html")
    d = EntryDetector()
    assert d.detect(tmp_path, unit="") == "a/index.html"
    assert d.detect(tmp_path, unit="all") == "a/index.html"
    assert d.detect(tmp_path, unit="整个项目") == "a/index.html"


def test_detect_unit_keyword_fallback(tmp_path):
    _write(tmp_path, "login.html")
    _write(tmp_path, "dashboard.html")
    assert EntryDetector().detect(tmp_path, unit="login") == "login.html"


def test_detect_unit_llm_pick(monkeypatch, tmp_path):
    _write(tmp_path, "login.html")
    _write(tmp_path, "dashboard.html")
    fake = _FakeLiteLLM(['{"entry": "login.html"}'])
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: fake)
    client = LLMClient(LLMConfig(roles={"gist": RoleConfig(model="gpt-4o-mini", temperature=0.1)}))
    assert EntryDetector(client).detect(tmp_path, unit="登录表单") == "login.html"
    assert len(fake.calls) == 1


def test_detect_fallback_when_no_html(tmp_path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    assert EntryDetector().detect(tmp_path, unit="全部") == "index.html"


def test_is_all_unit_semantics():
    assert is_all_unit("") is True
    assert is_all_unit("全部") is True
    assert is_all_unit("all") is True
    assert is_all_unit("整个项目") is True
    assert is_all_unit("登录表单") is False
