"""Divergent candidates and partial judgments survive browser, storage and reports."""
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


def install_divergent_models(monkeypatch, directory, judgment_status, empty_reason=None):
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
            if empty_reason is not None:
                payload = {"expectations": [], "abstention": {
                    "code": "insufficient_visible_basis", "reason": empty_reason}}
        elif role == "visual":
            payload = {"changes": ["other"], "summary": "本地页面的可见结果"}
        elif role == "judge":
            assert empty_reason is None, "空预期不能调用判定模型"
            step = load_snapshot(directory)["steps"][-1]
            assert step["execution_status"] == "completed"
            assert step["expectation_generation"]["coverage"] == "complete"
            assert len(step["expectations"]) == 2
            expectation = step["expectations"][0]
            payload = {"status": "mismatch" if judgment_status == "mixed" else judgment_status, "mismatches": []}
            if judgment_status in {"mismatch", "mixed"}:
                payload["mismatches"] = [{"expectation_id": expectation["id"], "expectation": expectation["text"],
                    "observation": "无保存反馈", "level": "medium", "reasoning": "操作结果未呈现"}]
                if judgment_status == "mixed":
                    payload.update(unverifiable_expectation_ids=[step["expectations"][1]["id"]], error="另一个要求被遮挡")
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


@pytest.mark.parametrize("judge_status", ["passed", "mismatch", "failed", "inconclusive", "mixed"])
def test_divergent_results_keep_findings_and_only_mark_actual_incomplete_checks(monkeypatch, http_base_url, tmp_path, judge_status):
    config = install_divergent_models(monkeypatch, tmp_path, judge_status)
    variant = 1 if judge_status == "passed" else 2
    pipeline = AlienQAPipeline(config, samples=2, max_actions=1, browser="chromium", artifacts_dir=tmp_path, verbose=False)
    result = pipeline.collect(ProjectLoader().load_browser(f"{http_base_url}/cognition-app/index.html?variant={variant}"))
    saved = load_snapshot(tmp_path)
    step = saved["steps"][0]
    expected_status = "mismatch" if judge_status == "mixed" else judge_status
    assert step["judgment_result"]["status"] == expected_status
    assert step["cognitive_status"] == expected_status
    assert result.incomplete == saved["incomplete"] == (judge_status in {"failed", "inconclusive", "mixed"})
    assert step["expectation_generation"]["groups"][0]["expectation_id"] == step["expectations"][0]["id"]
    if variant == 2:
        assert any(ev.finding_kind == "technical_anomaly" for ev in result.evidences)
    cognitive = [ev for ev in result.evidences if ev.finding_kind == "cognitive_mismatch"]
    assert len(cognitive) == (1 if judge_status in {"mismatch", "mixed"} else 0)
    if cognitive:
        assert cognitive[0].expectation_id == step["expectations"][0]["id"]


def test_relationship_warnings_visible_on_run_and_copied_offline_analysis(page, monkeypatch, http_base_url, tmp_path):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("fixture", mode="browser", base_url=f"{http_base_url}/cognition-app/index.html?variant=1")
    config = install_divergent_models(monkeypatch, rec.dir, "passed")
    pipeline = AlienQAPipeline(config, samples=2, max_actions=1, browser="chromium", run_dir=rec.dir,
                              run_id=rec.id, artifacts_dir=rec.dir / "artifacts", verbose=False)
    with ThreadPoolExecutor(1) as pool:
        result = pool.submit(pipeline.collect, ProjectLoader().load_browser(rec.base_url)).result()
    runs.finish(rec.id, "done")
    app.config["report_builder"] = ReportBuilder(pipeline.client)
    tab, errors = page
    with serve(app) as base_url:
        tab.goto(f"{base_url}/runs/{rec.id}")
        expect(tab.locator("body")).to_contain_text("检查覆盖：complete")
        expect(tab.locator("body")).to_contain_text("局部判定：passed")
        tab.get_by_text("事前采样要求与未决原因", exact=True).click()
        expect(tab.locator("body")).to_contain_text("打开陌生的业务面板")
        with tab.expect_download() as exported:
            tab.get_by_role("link", name="下载分析", exact=True).click()
        destination = tmp_path / "copied-analysis.html"
        exported.value.save_as(str(destination))
    assert not result.incomplete
    tab.context.set_offline(True)
    tab.goto(destination.as_uri())
    expect(tab.locator("body")).to_contain_text("检查覆盖：complete")
    expect(tab.locator("body")).to_contain_text("局部判定：passed")
    expect(tab.locator("body")).to_contain_text("打开陌生的业务面板")
    expect(tab.locator("body")).to_contain_text("采样关系备注")
    assert errors == []


def test_abstention_persists_to_online_and_offline_analysis(page, monkeypatch, http_base_url, tmp_path):
    reason = "当前可见资料不足以支持具体结果要求"
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("fixture", mode="browser", base_url=f"{http_base_url}/cognition-app/index.html?variant=1")
    config = install_divergent_models(monkeypatch, rec.dir, "passed", empty_reason=reason)
    pipeline = AlienQAPipeline(config, samples=2, max_actions=1, browser="chromium", run_dir=rec.dir,
                              run_id=rec.id, artifacts_dir=rec.dir / "artifacts", verbose=False)
    with ThreadPoolExecutor(1) as pool:
        result = pool.submit(pipeline.collect, ProjectLoader().load_browser(rec.base_url)).result()
    snapshot = load_snapshot(rec.dir)
    step = snapshot["steps"][0]
    assert step["execution_status"] == "completed" and step["cognitive_status"] == "inconclusive"
    assert step["expectation_generation"]["coverage_reason"] == "no_expectations"
    assert len(step["expectation_generation"]["empty_samples"]) == 2
    assert step["expectation_generation"]["samples"][0]["abstention"]["reason"] == reason
    assert result.incomplete and not step.get("judgment_result")
    runs.finish(rec.id, "partial")
    app.config["report_builder"] = ReportBuilder(pipeline.client)
    tab, errors = page
    with serve(app) as base_url:
        tab.goto(f"{base_url}/runs/{rec.id}")
        tab.get_by_text("事前采样要求与未决原因", exact=True).click()
        expect(tab.locator("body")).to_contain_text(reason)
        with tab.expect_download() as exported:
            tab.get_by_role("link", name="下载分析", exact=True).click()
        destination = tmp_path / "copied-abstention.html"
        exported.value.save_as(str(destination))
    tab.context.set_offline(True)
    tab.goto(destination.as_uri())
    expect(tab.locator("body")).to_contain_text(reason)
    expect(tab.locator("body")).to_contain_text("no_expectations")
    expect(tab.locator("body")).to_contain_text("扫描不完整")
    assert errors == []
