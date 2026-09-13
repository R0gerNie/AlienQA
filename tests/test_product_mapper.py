"""Product Mapper 测试：过滤、JSON 解析、白名单、端到端 map()（mock LLM）。"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from alienqa.llm import LLMClient, LLMConfig, RoleConfig
from alienqa.loader import Project, VisibleFile
from alienqa.mapper import Area, ProductMap, ProductMapper
from alienqa.mapper.filter import build_surface_text, filter_visible_files, read_readme


class _FakeLiteLLM:
    """按队列返回文本/异常，并记录每次调用的 kwargs。"""

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


@pytest.fixture
def fake_litellm(monkeypatch):
    fake = _FakeLiteLLM([])
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: fake)
    return fake


@pytest.fixture
def mapper(fake_litellm):
    cfg = LLMConfig(roles={"gist": RoleConfig(model="gpt-4o-mini", temperature=0.1)})
    return ProductMapper(LLMClient(cfg))


def _vf(path, role="unknown"):
    return VisibleFile(path=path, role=role, lines=10)


# ---- 过滤 ----

def test_filter_excludes_noise_and_sorts_by_role():
    project = Project(visible_files=[
        _vf("app/page.tsx", "page"),
        _vf("app/page.min.js", "unknown"),
        _vf("src/Button.test.tsx", "component"),
        _vf("node_modules/x/y.js", "unknown"),
        _vf("public/logo.svg", "copy"),
    ])
    paths = [f.path for f in filter_visible_files(project)]
    assert "app/page.tsx" in paths
    assert "public/logo.svg" in paths
    assert "app/page.min.js" not in paths
    assert "src/Button.test.tsx" not in paths
    assert "node_modules/x/y.js" not in paths
    # page 优先级高于 copy
    assert paths.index("app/page.tsx") < paths.index("public/logo.svg")


def test_build_surface_text_includes_routes_and_file_snippet(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "page.tsx").write_text(
        "export default function Page() {\n  return <div>Login</div>;\n}\n", encoding="utf-8"
    )
    project = Project(
        root=str(tmp_path),
        routes=["/login", "/orders"],
        entry_points=["app/page.tsx"],
        visible_files=[_vf("app/page.tsx", "page")],
    )
    text = build_surface_text(project, tmp_path)
    assert "/login" in text
    assert "app/page.tsx" in text
    assert "<div>Login</div>" in text


def test_read_readme_truncates(tmp_path):
    (tmp_path / "README.md").write_text("Hello " * 5000, encoding="utf-8")
    text = read_readme(tmp_path)
    assert text.startswith("Hello")
    assert len(text) <= 4000


# ---- JSON 解析与白名单 ----

def test_from_json_strips_fence_and_trailing():
    text = '```json\n{"areas":[{"name":"Auth","pages":["/login"]}]}\n```\n（完）'
    pm = ProductMap.from_json(text)
    assert len(pm.areas) == 1
    assert pm.areas[0].name == "Auth"
    assert pm.areas[0].pages == ["/login"]


def test_from_json_whitelist_drops_conclusions():
    text = (
        '{"areas":[{"name":"Orders","pages":["/orders"],'
        '"bugs":["结算按钮没反应"],"conclusion":"疑似有 bug"}],'
        '"relations":[],"issues":[1,2,3]}'
    )
    pm = ProductMap.from_json(text)
    assert len(pm.areas) == 1
    area = pm.areas[0]
    assert area.name == "Orders"
    assert not hasattr(area, "bugs")
    assert not hasattr(area, "conclusion")
    assert not hasattr(pm, "issues")


def test_from_json_missing_fields_default():
    pm = ProductMap.from_json('{"areas":[{"name":"Only Name"}]}')
    assert pm.areas[0].states == []
    assert pm.areas[0].pages == []
    assert pm.areas[0].entities == []


# ---- 端到端 map() ----

def test_map_end_to_end(mapper, fake_litellm, tmp_path):
    (tmp_path / "README.md").write_text("这是一个电商后台", encoding="utf-8")
    project = Project(root=str(tmp_path), routes=["/login", "/orders"], entry_points=["app/page.tsx"])
    fake_litellm.texts.extend([
        "这是一个电商后台，面向商家与管理员。",  # summarize_gist
        '{"areas":[{"name":"Auth","pages":["/login"],"actions":["login"]}],'
        '"relations":[{"from":"/login","to":"/orders","kind":"navigate"}]}',  # map_product
    ])
    result = mapper.map(project)
    assert result.brief == "这是一个电商后台，面向商家与管理员。"
    assert len(result.areas) == 1
    assert result.areas[0].name == "Auth"
    assert result.areas[0].actions == ["login"]
    assert result.relations[0].from_ == "/login"
    assert result.relations[0].to == "/orders"
    assert len(fake_litellm.calls) == 2  # gist + map_product


def test_map_retries_when_json_invalid(mapper, fake_litellm, tmp_path):
    project = Project(root=str(tmp_path), routes=["/a"])
    fake_litellm.texts.extend([
        "gist summary",
        "not json at all",                        # map_product #1 → 解析失败
        '{"areas":[{"name":"A","pages":["/a"]}]}',  # map_product #2 (repair)
    ])
    result = mapper.map(project)
    assert len(result.areas) == 1
    assert len(fake_litellm.calls) == 3  # gist + 2 map_product
    assert "不是合法 JSON" in fake_litellm.calls[2]["messages"][0]["content"]


def test_map_returns_empty_when_all_json_invalid(mapper, fake_litellm, tmp_path):
    project = Project(root=str(tmp_path))
    fake_litellm.texts.extend(["gist", "bad1", "bad2"])
    result = mapper.map(project)
    assert result.areas == []
    assert result.relations == []


def test_map_areas_returns_list_of_area(mapper, fake_litellm, tmp_path):
    project = Project(root=str(tmp_path), routes=["/a"])
    fake_litellm.texts.extend([
        "gist",
        '{"areas":[{"name":"A"},{"name":"B"}]}',
    ])
    areas = mapper.map_areas(project)
    assert [a.name for a in areas] == ["A", "B"]
    assert all(isinstance(a, Area) for a in areas)
