"""Partial cognition survives the real browser, storage, UI and offline report."""
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect

from alienqa.llm import LLMConfig, Role, RoleConfig
from alienqa.loader import ProjectLoader
from alienqa.mapper import ProductMap
from alienqa.pipeline import AlienQAPipeline
from alienqa.review import ReportBuilder
from alienqa.run_writer import load_snapshot
from test_sampling_calibration import row
from test_t06_browser_flow import serve
from test_ui_app import _make_app
from test_ui_browser_flow import page


def install_partial_models(monkeypatch, directory, judgment_status):
    sample_number = 0
    def completion(**kwargs):
        nonlocal sample_number
        role = kwargs["model"].split("/")[-1]
        if role == "expectation":
            sample_number += 1
            rows = [row("保存后应说明操作结果")]
            if sample_number == 2:
                rows.append(row("打开陌生的业务面板"))
            payload = {"expectations": rows}
        elif role == "visual":
            payload = {"changes": ["other"], "summary": "本地页面的可见结果"}
        elif role == "judge":
            step = load_snapshot(directory)["steps"][-1]
            assert step["execution_status"] == "completed"
            assert step["expectation_generation"]["coverage"] == "partial"
            expectation = step["expectations"][0]
            payload = {"status": judgment_status, "mismatches": []}
            if judgment_status == "mismatch":
                payload["mismatches"] = [{"expectation_id": expectation["id"], "expectation": expectation["text"],
                    "observation": "无保存反馈", "level": "medium", "reasoning": "操作结果未呈现"}]
            elif judgment_status in {"failed", "inconclusive"}:
                payload["error"] = "判定未完成"
        elif role == "reporter":
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=""))], usage=None)
        else:
            payload = {"root_cause_hypothesis": "待复核", "reproduction_steps": [], "technical_evidence": {}, "affected_components": []}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))], usage=None)
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: SimpleNamespace(completion=completion))
    monkeypatch.setattr("alienqa.pipeline.ProductMapper.map_from_browser", lambda *args: ProductMap())
    return LLMConfig(roles={role.value: RoleConfig(model=f"test/{role.value}") for role in Role})


@pytest.mark.parametrize("judge_status", ["passed", "mismatch", "failed", "inconclusive"])
def test_partial_results_keep_local_judgment_and_incomplete_state(monkeypatch, http_base_url, tmp_path, judge_status):
    config = install_partial_models(monkeypatch, tmp_path, judge_status)
    variant = 1 if judge_status == "passed" else 2
    pipeline = AlienQAPipeline(config, samples=2, max_actions=1, browser="chromium", artifacts_dir=tmp_path, verbose=False)
    result = pipeline.collect(ProjectLoader().load_browser(f"{http_base_url}/cognition-app/index.html?variant={variant}"))
    saved = load_snapshot(tmp_path)
    step = saved["steps"][0]
    assert step["judgment_result"]["status"] == judge_status
    assert step["cognitive_status"] == ("inconclusive" if judge_status == "passed" else judge_status)
    assert result.incomplete and saved["incomplete"]
    assert step["expectation_generation"]["groups"][0]["expectation_id"] == step["expectations"][0]["id"]
    if variant == 2:
        assert any(ev.finding_kind == "technical_anomaly" for ev in result.evidences)
    cognitive = [ev for ev in result.evidences if ev.finding_kind == "cognitive_mismatch"]
    assert len(cognitive) == (1 if judge_status == "mismatch" else 0)
    if cognitive:
        assert cognitive[0].expectation_id == step["expectations"][0]["id"]


def test_partial_diagnostics_visible_on_run_and_copied_offline_analysis(page, monkeypatch, http_base_url, tmp_path):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("fixture", mode="browser", base_url=f"{http_base_url}/cognition-app/index.html?variant=1")
    config = install_partial_models(monkeypatch, rec.dir, "passed")
    pipeline = AlienQAPipeline(config, samples=2, max_actions=1, browser="chromium", run_dir=rec.dir,
                              run_id=rec.id, artifacts_dir=rec.dir / "artifacts", verbose=False)
    with ThreadPoolExecutor(1) as pool:
        result = pool.submit(pipeline.collect, ProjectLoader().load_browser(rec.base_url)).result()
    runs.finish(rec.id, "partial")
    app.config["report_builder"] = ReportBuilder(pipeline.client)
    tab, errors = page
    with serve(app) as base_url:
        tab.goto(f"{base_url}/runs/{rec.id}")
        expect(tab.locator("body")).to_contain_text("检查覆盖：partial")
        expect(tab.locator("body")).to_contain_text("局部判定：passed")
        tab.get_by_text("事前采样要求与未决原因", exact=True).click()
        expect(tab.locator("body")).to_contain_text("打开陌生的业务面板")
        with tab.expect_download() as exported:
            tab.get_by_role("link", name="下载分析", exact=True).click()
        destination = tmp_path / "copied-analysis.html"
        exported.value.save_as(str(destination))
    assert result.incomplete
    tab.context.set_offline(True)
    tab.goto(destination.as_uri())
    expect(tab.locator("body")).to_contain_text("检查覆盖：partial")
    expect(tab.locator("body")).to_contain_text("局部判定：passed")
    expect(tab.locator("body")).to_contain_text("打开陌生的业务面板")
    expect(tab.locator("body")).to_contain_text("扫描不完整")
    assert errors == []
