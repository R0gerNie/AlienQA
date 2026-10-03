"""Report chrome uses the selected language without rewriting recorded evidence."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest

from alienqa.evidence import Evidence
from alienqa.review import Decision, ReportBuilder, ReviewState
from alienqa.review.report import render_report_html


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden -= 1

    def handle_data(self, text):
        if not self.hidden:
            self.text.append(text)


def _builder(language="zh"):
    builder = ReportBuilder(SimpleNamespace(config=SimpleNamespace(language=language)))
    builder.roles.compose_report = lambda *args, **kwargs: ""
    return builder


def test_empty_analysis_is_english_and_chinese_remains_default():
    report = _builder().build([], ReviewState(), mode="analysis", language="en")
    assert '<html lang="en">' in report.html
    for text in ("QA and User Cognition Analysis", "Scan Scope and Completeness", "Save all choices", "Generate final report"):
        assert text in report.html
    parser = _VisibleText()
    parser.feed(report.html)
    assert not re.search(r"[\u4e00-\u9fff]", "".join(parser.text))
    assert '<html lang="zh">' in _builder().build([], ReviewState(), mode="analysis").html
    assert '跳到报告内容' in render_report_html("<p>source</p>")
    assert 'Skip to report content' in render_report_html("<p>source</p>", language="en")


def test_english_report_preserves_user_evidence_and_model_receives_language(tmp_path):
    builder = _builder()
    calls = []
    builder.roles.compose_report = lambda records, **kwargs: calls.append((json.loads(records), kwargs)) or ""
    evidence = Evidence(id="EV", finding_kind="technical_anomaly", expectation="保存全部选择",
                        observation_summary="观察原声", reasoning="推理原文", expectation_basis={"reference": "备注"},
                        artifacts={"after": "missing.png", "technical": "missing.json", "dom": "missing.html"},
                        replay={"url": "https://example.test", "target_action": {"type": "fill", "target": {"text": "保存此条"}, "text": "输入原文"}})
    state = ReviewState()
    state.decide("EV", Decision.REJECTED, "用户备注")
    investigation = SimpleNamespace(issue_id="", status="failed", error="专家原声")
    report = builder.build([evidence], state, [investigation], diagnostics=[{"error": "诊断原文"}],
        mode="analysis", language="en", scan_context={"run_dir": str(tmp_path), "run_id": "run-en", "status": "partial", "base_url": "https://example.test"})
    for source in ("保存全部选择", "观察原声", "推理原文", "备注", "保存此条", "输入原文", "用户备注", "诊断原文"):
        assert source in report.html
    for chrome in ("Scan incomplete", "Before action", "After action", "screenshot file is unavailable", "DOM record cannot be read", "Recorded decision and note", "Root cause hypothesis", "LLM calls and usage"):
        assert chrome in report.html
    assert calls[0][1]["language"] == "en"
    assert calls[0][0][0]["reproduction"] == ["Open the initial page https://example.test", "fill 保存此条 Enter: 输入原文"]
    assert "Technical record cannot be read" in calls[0][0][0]["technical_signals"]["artifact_error"]


def test_language_precedence_and_shared_builder_do_not_leak():
    builder = _builder("en")
    assert '<html lang="en">' in builder.build([], ReviewState(), mode="analysis").html
    assert '<html lang="zh">' in builder.build([], ReviewState(), mode="analysis", scan_context={"language": "zh"}).html
    assert '<html lang="en">' in builder.build([], ReviewState(), mode="analysis", scan_context={"language": "zh"}, language="en").html
    with ThreadPoolExecutor(2) as pool:
        reports = list(pool.map(lambda lang: builder.build([], ReviewState(), mode="analysis", language=lang), ["en", "zh"] * 5))
    assert all(f'<html lang="{lang}">' in report.html for lang, report in zip(["en", "zh"] * 5, reports))
    assert builder.client.config.language == "en"


def test_detailed_english_chrome_contains_no_untranslated_builtin_text(tmp_path):
    (tmp_path / "shot.png").write_bytes(b"image")
    (tmp_path / "unsupported.txt").write_text("image")
    (tmp_path / "dom.html").write_text("<main>recorded DOM</main>")
    (tmp_path / "signals.json").write_text('{"records": []}')
    evidence = Evidence(id="EV", issue_id="group", finding_kind="technical_anomaly", step_id="step",
                        artifacts={"before": "shot.png", "after": "unsupported.txt", "technical": "signals.json", "dom": "dom.html"},
                        replay={"storage_state": "local-private-state"})
    investigation = SimpleNamespace(issue_id="group", evidence_ids=["EV"], status="failed", error="Expert unavailable",
                                    root_cause_hypothesis="", reproduction_steps=["Open the page"],
                                    technical_evidence={"signal": "timeout"}, input_status={"status": "partial"})
    step = {"step_id": "step", "expectation_generation": {"coverage": "partial", "sampling": {"complete": False},
            "relationship_warnings": ["Unresolved relationship"]},
            "judgment_result": {"status": "partial", "unverifiable_expectation_ids": ["EXP"]}}
    report = _builder().build([evidence], ReviewState(), [investigation], mode="analysis", language="en",
        scan_context={"run_id": "en-detailed", "run_dir": str(tmp_path), "status": "timeout", "steps": [step]})
    parser = _VisibleText()
    parser.feed(report.html)
    assert not re.search(r"[\u4e00-\u9fff]", "".join(parser.text))
    assert "Expert investigation failed" in report.html
    assert "The original scan collected 1 finding<" in report.html
    assert 'data-findings-count>1 finding<' in report.html
    assert "Sampling completion" in report.html
    assert "screenshot format cannot be embedded" in report.html


def test_offline_localized_json_cannot_terminate_embedded_script(monkeypatch):
    from alienqa.review import offline_review
    attack = '</script><img src=x onerror="window.PWN=1">\u2028\u2029&'
    monkeypatch.setattr(offline_review, "t", lambda *args, **kwargs: attack)
    script = offline_review.render_offline_review_script("en")
    assert script.count("</script>") == 1
    assert "<img" not in script
    assert "\\u003c/script\\u003e" in script
    assert "\\u2028\\u2029\\u0026" in script


@pytest.mark.parametrize("decision,match", [(Decision.PENDING, "has not been reviewed"), (Decision.SKIPPED, "must clear by-design/skipped")])
def test_confirmed_report_validation_errors_follow_language(decision, match):
    state = ReviewState()
    state.decide("EV", decision)
    with pytest.raises(ValueError, match=match):
        _builder().build([Evidence(id="EV")], state, language="en")
