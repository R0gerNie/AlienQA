"""Language selection before parsing and propagation without model/browser calls."""
import json
import re
from types import SimpleNamespace

import pytest

from alienqa import __main__ as cli
from alienqa.pipeline import PipelineResult


def test_english_help_is_selected_before_parsing(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--language", "en", "--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "AlienQA end-to-end testing" in output
    assert "--language {zh,en}" in output
    assert "LLM configuration YAML" in output
    assert not re.search(r"[\u4e00-\u9fff]", output)


def test_default_help_remains_chinese(monkeypatch, capsys):
    monkeypatch.delenv("ALIENQA_LANGUAGE", raising=False)
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "全链路测试" in capsys.readouterr().out


def test_english_input_errors_are_translated(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--language", "en", "--url", "http://:8000"])
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert "URL" in error
    assert "unrecognized arguments" not in error
    assert not re.search(r"[\u4e00-\u9fff]", error)


@pytest.mark.parametrize("flags,config_language,environment,expected", [
    ([], None, "en", "en"),
    ([], "en", "zh", "en"),
    (["--language", "zh"], "en", "en", "zh"),
])
def test_cli_language_precedence_for_help(tmp_path, monkeypatch, capsys,
                                          flags, config_language, environment, expected):
    config = tmp_path / "models.yaml"
    config.write_text("llm:\n  roles: {}\n" + (f"  language: {config_language}\n" if config_language else ""))
    monkeypatch.setenv("ALIENQA_LANGUAGE", environment)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--config", str(config), *flags, "--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert ("AlienQA end-to-end testing" in output) == (expected == "en")


def test_argv_none_uses_process_arguments(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "argv", ["alienqa", "--language=en", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert "AlienQA end-to-end testing" in capsys.readouterr().out


def test_english_language_reaches_pipeline_record_and_report(tmp_path, monkeypatch, capsys):
    calls = {}

    class Pipeline:
        def __init__(self, config, **kwargs):
            calls["config"] = config
            self.client = SimpleNamespace()

        def collect(self, project):
            return PipelineResult()

    class Builder:
        def __init__(self, client):
            pass

        def build(self, *args, **kwargs):
            calls["report"] = kwargs
            return SimpleNamespace(html="<html lang='en'>English report</html>")

    monkeypatch.setattr(cli, "AlienQAPipeline", Pipeline)
    monkeypatch.setattr(cli, "ReportBuilder", Builder)
    monkeypatch.setattr(cli, "check_browser", lambda _: None)
    monkeypatch.setattr(cli, "check_url", lambda _: None)
    monkeypatch.setattr(cli, "_load_keys", lambda: None)
    directory = tmp_path / "scan"
    assert cli.main(["--language", "en", "--url", "https://app.test/",
                     "--artifacts-dir", str(directory)]) == 0
    assert calls["config"].language == "en"
    assert calls["report"]["language"] == "en"
    assert calls["report"]["scan_context"]["language"] == "en"
    assert json.loads((directory / "run.json").read_text())["language"] == "en"
    assert not re.search(r"[\u4e00-\u9fff]", capsys.readouterr().out)


def test_english_console_startup_receives_language(monkeypatch, capsys):
    import alienqa.ui

    calls = {}

    def create_ui_app(*args, **kwargs):
        calls.update(kwargs)
        return SimpleNamespace(run=lambda **_: None)

    monkeypatch.setattr(alienqa.ui, "create_ui_app", create_ui_app)
    monkeypatch.setattr(cli, "_load_keys", lambda: None)
    assert cli.main(["--ui", "--language", "en"]) == 0
    assert calls["language"] == "en"
    assert "Console:" in capsys.readouterr().out


@pytest.mark.parametrize("flags,expected", [([], "en"), (["--language", "zh"], "zh")])
def test_saved_review_keeps_run_language_unless_overridden(tmp_path, monkeypatch, flags, expected):
    from alienqa.run_writer import RunWriter

    monkeypatch.delenv("ALIENQA_LANGUAGE", raising=False)
    RunWriter(tmp_path, tmp_path.name).checkpoint(phase="terminal", steps=[], evidences=[], diagnostics=[])
    (tmp_path / "run.json").write_text(json.dumps({"status": "done", "language": "en"}))
    calls = {}

    def create_app(*args, **kwargs):
        calls.update(kwargs)
        return SimpleNamespace(config={}, run=lambda **_: None)

    monkeypatch.setattr(cli, "create_app", create_app)
    monkeypatch.setattr(cli, "_load_keys", lambda: None)
    assert cli.main(["--review-run", str(tmp_path), *flags]) == 0
    assert calls["language"] == expected
    assert calls["scan_context"]["language"] == expected
