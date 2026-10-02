"""Real scan → native review → changed analysis → copied offline HTML (stub LLM)."""
import json
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server

from alienqa.llm import LLMConfig, Role, RoleConfig
from alienqa.loader import ProjectLoader
from alienqa.mapper import ProductMap
from alienqa.pipeline import AlienQAPipeline
from alienqa.review import HumanReview, ReportBuilder, create_app
from alienqa.run_writer import load_snapshot
from test_ui_app import _make_app
from test_ui_browser_flow import page


@contextmanager
def serve(app):
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(1)


@pytest.mark.parametrize("surface", ["main", "standalone"])
def test_real_scan_review_download_and_offline(surface, page, http_base_url, tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("fixture", mode="browser", base_url=f"{http_base_url}/cognition-app/index.html?variant=2")
    expected = "保存后应出现可见反馈"
    def completion(**kwargs):
        role = kwargs["model"].split("/")[-1]
        if role == "expectation":
            text = json.dumps({"expectations": [{"text": expected, "expectation_basis": {"type": "visible_copy", "reference": "保存"}}]})
        elif role == "visual":
            text = '{"changes":["other"],"summary":"未见保存结果"}'
        elif role == "judge":
            exp = load_snapshot(rec.dir)["steps"][-1]["expectations"][0]
            text = json.dumps({"status": "mismatch", "mismatches": [{"expectation_id": exp["id"], "expectation": expected,
                "observation": "无反馈", "level": "medium", "reasoning": "按钮承诺了保存操作"}]})
        elif role == "reporter":
            text = '<script>window.PWN=1</script><img src="https://evil.test" onerror="window.PWN=2"><p>解释补充</p>'
        else:
            text = "invalid investigation JSON"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=None)
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: SimpleNamespace(completion=completion))
    monkeypatch.setattr("alienqa.pipeline.ProductMapper.map_from_browser", lambda *args: ProductMap())
    config = LLMConfig(roles={role.value: RoleConfig(model=f"test/{role.value}") for role in Role})
    pipeline = AlienQAPipeline(config, samples=1, max_actions=1, browser="chromium", artifacts_dir=rec.dir / "artifacts",
                              run_dir=rec.dir, run_id=rec.id, verbose=False)
    # The review browser owns this thread's Playwright loop; scan owns another.
    with ThreadPoolExecutor(1) as pool:
        result = pool.submit(pipeline.collect, ProjectLoader().load_browser(rec.base_url)).result()
    assert {e.finding_kind for e in result.evidences} == {"technical_anomaly", "cognitive_mismatch"}
    assert result.incomplete and result.diagnostics
    runs.finish(rec.id, "partial", evidence_count=len(result.evidences), issue_count=len(result.issues))
    cognitive = next(e for e in result.evidences if e.finding_kind == "cognitive_mismatch")
    builder = ReportBuilder(pipeline.client)
    if surface == "main":
        app.config["report_builder"] = builder
        base_path = f"/runs/{rec.id}"
        review_path = base_path + "/review"
    else:
        snapshot = runs.load_report_snapshot(rec.id)
        app = create_app(HumanReview(), builder, investigations=result.investigations,
                         review_path=str(rec.dir / "review.json"), scan_context=snapshot["scan_context"])
        app.config["evidences"] = result.evidences
        app.config["diagnostics"] = snapshot["diagnostics"]
        base_path, review_path = "", "/"
    tab, errors = page
    with serve(app) as base_url:
        tab.goto(base_url + review_path)
        row = tab.locator(f'[data-review="{cognitive.id}"]')
        expect(row.get_by_role("combobox")).to_have_value("pending")
        if surface == "main":
            expect(tab.get_by_role("button", name="重放", exact=True)).to_have_count(len(result.evidences))
        row.get_by_role("combobox").select_option("by-design")
        note = '按设计：请保留原声 <script>window.PWN=3</script>'
        row.get_by_role("textbox").fill(note)
        with tab.expect_response(lambda r: r.url.endswith(base_path + "/decide") and r.request.method == "POST") as saved:
            row.get_by_role("button", name="保存决定").click()
        assert saved.value.request.post_data_json == {"evidence_id": cognitive.id, "decision": "by-design", "note": note}
        expect(row.locator('[role="status"]')).to_contain_text("已保存")
        tab.reload()
        expect(row.get_by_role("combobox")).to_have_value("by-design")
        expect(row.get_by_role("textbox")).to_have_value(note)
        expect(tab.locator('select[name="decision"]').filter(has=tab.locator('option[value="pending"]:checked'))).to_have_count(len(result.evidences) - 1)
        assert tab.request.get(base_url + base_path + "/report").status == 409
        with tab.expect_download() as exported:
            tab.get_by_role("link", name="下载分析", exact=True).click()
        old = tmp_path / "copied" / "old-analysis.html"
        old.parent.mkdir()
        exported.value.save_as(str(old))
        assert "by-design" in old.read_text() and "pending" in old.read_text()
        row.get_by_role("combobox").select_option("confirmed")
        row.get_by_role("textbox").fill("现在确认：仍保留原始依据")
        row.get_by_role("button", name="保存决定").click()
        expect(row.locator('[role="status"]')).to_contain_text("已保存：确认问题")
        assert not (rec.dir / "analysis.html").exists()
        with tab.expect_download() as exported:
            tab.get_by_role("link", name="下载分析", exact=True).click()
        output = old.parent / "analysis.html"
        exported.value.save_as(str(output))
    tab.context.set_offline(True)
    tab.goto(output.as_uri())
    expect(tab.locator("section")).to_have_count(len(result.evidences))
    expect(tab.locator("body")).to_contain_text("现在确认：仍保留原始依据")
    expect(tab.locator("body")).to_contain_text("扫描不完整")
    expect(tab.locator("body")).to_contain_text("fixture action exception")
    expect(tab.locator("body")).to_contain_text("事前依据")
    assert tab.locator("img").count() >= 2
    assert tab.locator("img").evaluate_all("images => images.every(img => img.complete && img.naturalWidth > 0)")
    assert tab.evaluate("window.PWN") is None and tab.locator("script").count() == 0
    assert errors == []


@pytest.mark.parametrize("surface", ["main", "standalone"])
@pytest.mark.parametrize("failure", ["network", "server", "invalid"])
def test_failed_save_retains_edits_and_can_retry(surface, failure, page, tmp_path):
    from alienqa.evidence import Evidence
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("test")
    runs.save_results(rec.id, [Evidence(id="EV")], [])
    runs.finish(rec.id, "done")
    if surface == "standalone":
        app = create_app(HumanReview(), ReportBuilder(SimpleNamespace()), scan_context={"status": "done"})
        app.config["evidences"] = [Evidence(id="EV")]
        path, endpoint = "/", "/decide"
    else:
        path, endpoint = f"/runs/{rec.id}/review", f"/runs/{rec.id}/decide"
    tab, errors = page
    with serve(app) as base_url:
        tab.goto(base_url + path)
        row = tab.locator('[data-review="EV"]')
        row.get_by_role("combobox").select_option("skipped")
        row.get_by_role("textbox").fill("不能丢失的编辑")
        def intercept(route):
            if failure == "network":
                route.abort()
            elif failure == "server":
                route.fulfill(status=500, content_type="application/json", body='{"error":"磁盘不可写"}')
            else:
                route.fulfill(status=200, content_type="text/html", body="not json")
        tab.route("**" + endpoint, intercept)
        row.get_by_role("button", name="保存决定").click()
        expect(row.locator('[role="status"]')).to_contain_text("保存失败")
        expect(row.get_by_role("button", name="保存决定")).to_be_enabled()
        expect(row.get_by_role("textbox")).to_have_value("不能丢失的编辑")
        tab.unroute("**" + endpoint)
        row.get_by_role("button", name="保存决定").click()
        expect(row.locator('[role="status"]')).to_contain_text("已保存：暂跳过")
        tab.reload()
        expect(row.get_by_role("textbox")).to_have_value("不能丢失的编辑")
    assert errors == []
