"""Runtime translations preserve observed labels and structured machine data."""
import json

import pytest

from alienqa.driver import Action, PlaywrightDriver, Target
from alienqa.driver.action import describe_visible_action
from alienqa.i18n import language_context
from alienqa.llm import LLMClient, LLMConfig
from alienqa.llm.codex import CodexProvider
from alienqa.llm.metering import MeteringSink, load_summary
from alienqa.loader import ProjectLoader, is_all_unit
from alienqa.loader.artifacts import validate_html
from alienqa.replay import ReplayEngine
from alienqa.static_server import normalize_base_path


def test_english_model_errors_follow_config_without_ambient_language():
    client = LLMClient(LLMConfig(language="en"))
    with pytest.raises(ValueError, match="No model is configured"):
        client.complete("judge", [])
    with pytest.raises(ValueError, match="No model is configured"):
        client.model_for("judge")
    with pytest.raises(ValueError, match="未配置"):
        LLMClient(LLMConfig()).model_for("judge")


def test_vision_keeps_language_instruction_in_system_message(monkeypatch):
    client = LLMClient(LLMConfig(language="en"))
    calls = []
    monkeypatch.setattr(client, "complete", lambda role, messages: calls.append((role, messages)))
    client.complete_vision("judge", "Compare these images", [b"first", b"second"], system="Write in English")
    role, messages = calls[0]
    assert role == "judge"
    assert messages[0] == {"role": "system", "content": "Write in English"}
    assert messages[1]["content"][0]["text"] == "Compare these images"
    assert len(messages[1]["content"]) == 3


def test_codex_preflight_error_uses_config_language(monkeypatch):
    monkeypatch.setattr("alienqa.llm.codex.shutil.which", lambda binary: None)
    with pytest.raises(RuntimeError, match="Codex CLI is not installed"):
        CodexProvider(LLMConfig(language="en"))
    with pytest.raises(RuntimeError, match="未安装 Codex CLI"):
        CodexProvider(LLMConfig())


def test_visible_action_translates_only_generated_description():
    labeled = Action("click", Target(text="保存", selector="#private-locator"))
    unlabeled = Action("click", Target(role="button", visible={"popup": "menu", "position": {
        "x": 1, "y": 2, "width": 20, "height": 10}}))
    with language_context("en"):
        assert describe_visible_action(labeled) == "click 保存"
        description = describe_visible_action(unlabeled)
    assert description == "click Unlabeled button (page position x=1, y=2), opens menu"
    assert "private-locator" not in description
    assert "无文案" in describe_visible_action(unlabeled)


def test_english_preparation_and_action_errors(tmp_path):
    with language_context("en"):
        with pytest.raises(ValueError, match="deployment base path"):
            normalize_base_path("relative/path")
        with pytest.raises(ValueError, match="No runnable HTML entry"):
            validate_html(tmp_path, "missing.html")
        with pytest.raises(FileNotFoundError, match="The input does not exist"):
            ProjectLoader().load(tmp_path / "missing")
        driver = PlaywrightDriver()
        with pytest.raises(ValueError, match="Unknown action type"):
            driver._perform(Action("unknown"), None, 1)
        with pytest.raises(ValueError, match="Coordinate fallback does not support"):
            driver._perform_at_coords(Action("type"), 1, 2)
    assert is_all_unit("All pages")
    assert is_all_unit("Entire project")


def test_replay_localized_notes_keep_status_and_source_data(monkeypatch):
    engine = ReplayEngine()
    monkeypatch.setattr(engine, "_load", lambda evidence_id: {"replay": {"package_version": 2}})
    with language_context("en"):
        result = engine.replay("EV-00001")
    assert result.status == "failed"
    assert result.note == "The replay package has no initial URL"
    assert result.limits[0].startswith("Similar screenshots")
    assert result.target_window == {"phase": None, "step_id": None, "action_id": None}


def test_saved_usage_notice_uses_scan_language_and_reads_allow_override(tmp_path):
    sink = MeteringSink(tmp_path, "RUN")
    sink.initialize(LLMConfig(language="en"))
    summary = sink.write_summary()
    assert summary["notice"].startswith("Only action and time budgets")
    assert summary["configuration"]["language"] == "en"
    assert summary["attempts"] == 0
    assert json.loads((tmp_path / "usage-summary.json").read_text())["notice"] == summary["notice"]
    assert load_summary(tmp_path, "RUN", language="zh")["notice"].startswith("仅有动作")
