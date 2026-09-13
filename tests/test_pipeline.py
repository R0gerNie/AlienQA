"""AlienQAPipeline 与 CLI 正式入口的单元测试（不触发真实 LLM/浏览器）。"""
from alienqa.driver import Action, Target
from alienqa.llm import LLMConfig, RoleConfig
from alienqa.pipeline import AlienQAPipeline, PipelineResult, _action_label, _describe_candidates
from alienqa.planner import Candidate
from alienqa.review import Report


def test_pipeline_result_html_without_report():
    result = PipelineResult()
    assert result.html == ""


def test_pipeline_constructs_with_config():
    cfg = LLMConfig(roles={"gist": RoleConfig(model="deepseek/deepseek-chat")})
    p = AlienQAPipeline(cfg, samples=1, headless=True, max_actions=1, verbose=False)
    assert p.client.config is cfg
    assert p.max_actions == 1


def test_pipeline_focus_derived_from_unit():
    cfg = LLMConfig(roles={"gist": RoleConfig(model="deepseek/deepseek-chat")})
    p = AlienQAPipeline(cfg, unit="登录表单", instructions="错误密码应有提示", verbose=False)
    assert p.unit == "登录表单"
    assert p.instructions == "错误密码应有提示"
    assert p.focus == "单元：登录表单\n指令：错误密码应有提示"


def test_collect_browser_launches_before_map(monkeypatch):
    from alienqa.loader import ProjectLoader
    from alienqa.mapper import ProductMap

    order = []

    class _FakeDriver:
        def __init__(self, headless=True, browser="chrome"):
            pass

        def launch(self, url, storage_state=None):
            order.append(("launch", url, storage_state))

        def close(self):
            pass

        def screenshot(self):
            return b"img"

        def visible_text(self):
            return "页面文字"

        def url(self):
            return "http://x/"

        def interactive_elements(self):
            return []

    monkeypatch.setattr("alienqa.pipeline.PlaywrightDriver", _FakeDriver)
    pipeline = AlienQAPipeline(LLMConfig(roles={}), verbose=False)
    pipeline._map_from_browser = lambda driver, project: (order.append(("map",)) or ProductMap())
    pipeline.collect(ProjectLoader().load_browser("http://x/"))
    kinds = [k for k, *_ in order]
    assert kinds[0] == "launch"
    assert kinds[1] == "map"


def test_map_from_browser_empty_surface_returns_empty_pm():
    pipeline = AlienQAPipeline(LLMConfig(roles={}), verbose=False)

    class _D:
        def visible_text(self):
            return "   "

    pm = pipeline._map_from_browser(_D(), None)
    assert pm.areas == []
    assert pm.brief == ""


def test_pipeline_result_html():
    report = Report(html="<p>x</p>", accepted_count=1, total_count=2)
    result = PipelineResult(report=report)
    assert result.html == "<p>x</p>"
    assert result.report.accepted_count == 1
    assert result.report.total_count == 2


def test_describe_candidates():
    candidates = [
        Candidate(action=Action("click", Target(text="Greet")), tag="button", text="Greet"),
        Candidate(action=Action("click", Target(selector="#name")), tag="input", text=""),
    ]
    out = _describe_candidates(candidates)
    assert "button「Greet」" in out
    assert "input" in out


def test_action_label():
    assert _action_label(Action("click", Target(text="Greet"))) == "click Greet"
    assert _action_label(Action("click", Target(selector="#name"))) == "click #name"


def test_cli_build_project(tmp_path):
    from alienqa.__main__ import _build_project

    p = _build_project(
        tmp_path,
        "http://127.0.0.1:9/demo-app/index.html",
        "Static HTML",
        "/demo-app,/other",
        "demo-app/index.html",
    )
    assert p.root == str(tmp_path)
    assert p.base_url == "http://127.0.0.1:9/demo-app/index.html"
    assert p.routes == ["/demo-app", "/other"]
    assert p.entry_points == ["demo-app/index.html"]
    assert p.visible_files[0].path == "demo-app/index.html"
