"""Subscription CLI transport, with fake processes in the normal test suite."""
import json
from types import SimpleNamespace

import pytest

from alienqa.llm import LLMClient, LLMConfig, RoleConfig
from alienqa.llm.metering import MeteringSink, load_summary


def events(text="answer", usage=None):
    return '\n'.join(json.dumps(event) for event in [
        {"type": "thread.started", "thread_id": "test-thread"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
        {"type": "turn.completed", "usage": usage or {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 3}},
    ])


@pytest.fixture
def rig(tmp_path, monkeypatch):
    import alienqa.llm.codex as module
    calls, behavior = [], [events()]
    monkeypatch.setattr(module.shutil, "which", lambda binary: "/fake/codex")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs:
        SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT", stderr=""))

    class Process:
        returncode = 0
        pid = 123456

        def __init__(self, args, **kwargs):
            from pathlib import Path
            self.args, self.kwargs = args, kwargs
            self.directory = Path(kwargs["cwd"])
            calls.append(self)
            if any(arg == "exec" for arg in args):
                summary = load_summary(tmp_path, "RUN")
                assert summary["counts"]["started"] == 1

        def communicate(self, input=None, timeout=None):
            self.input, self.timeout = input, timeout
            from pathlib import Path
            self.images = [Path(self.args[index + 1]).read_bytes()
                           for index, argument in enumerate(self.args) if argument == '--image']
            self.instructions = (self.directory / "instructions.txt").read_text()
            item = behavior.pop(0)
            if isinstance(item, Exception):
                raise item
            return item, ""

        def wait(self, timeout=None):
            return self.returncode

    monkeypatch.setattr(module.subprocess, "Popen", Process)
    sink = MeteringSink(tmp_path, "RUN")
    config = LLMConfig.from_dict({"llm": {"codex": {"reasoning_effort": "low"}, "roles": {
        role: {"model": "codex/gpt-6.1-sol"} for role in ("gist", "expectation", "visual", "judge", "investigator", "reporter")}}})
    sink.initialize(config)
    client = LLMClient(config, sink=sink)
    return SimpleNamespace(client=client, sink=sink, config=config, calls=calls, behavior=behavior, module=module,
                           summary=lambda: load_summary(tmp_path, "RUN"))


@pytest.mark.parametrize("role", ["gist", "expectation", "visual", "judge", "investigator", "reporter"])
def test_six_roles_use_existing_login_with_isolated_context(rig, role, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-use-api-key")
    monkeypatch.setenv("CODEX_HOME", "/existing/auth/home")
    result = rig.client.complete(role, [{"role": "user", "content": "only supplied context"}])
    assert result.text == "answer"
    call = rig.calls[0]
    assert call.kwargs["env"]["CODEX_HOME"] == "/existing/auth/home"
    assert "OPENAI_API_KEY" not in call.kwargs["env"]
    for arg in ("--ignore-user-config", "--ephemeral", "--json", "read-only", "features.shell_tool=false",
                "project_doc_max_bytes=0", 'forced_login_method="chatgpt"', 'web_search="disabled"'):
        assert arg in call.args
    assert "only supplied context" in call.input
    assert not call.directory.exists()
    summary = rig.summary()
    assert summary["attempts"] == 1 and summary["unknown_cost_attempts"] == 1
    assert summary["tokens"]["prompt_tokens"]["known"] == 10
    assert summary["tokens"]["completion_tokens"]["known"] == 3
    assert summary["attempt_units"] == {"cli_invocation": 1}
    settings = rig.sink.read_calls()[0]["attempts"][0]["config"]
    assert settings["temperature"] is None and settings["requested_temperature"] == .2
    assert settings["reasoning_effort"] == "low"


def test_vision_passes_images_as_local_attachments_without_base64_prompt(rig, monkeypatch):
    from pathlib import Path
    original_glob = Path.glob
    monkeypatch.setattr(Path, 'glob', lambda directory, pattern: iter(reversed(list(original_glob(directory, pattern)))))
    rig.client.complete_vision("judge", "compare", [b"first-image", b"second-image"])
    call = rig.calls[0]
    assert call.images == [b"first-image", b"second-image"]
    assert call.args.count("--image") == 2 and "base64" not in call.input
    assert "Image 1" in call.input and "Image 2" in call.input


def test_startup_warning_is_preserved_but_not_mistaken_for_model_tool_use(rig):
    warning = json.dumps({"type": "item.completed", "item": {"type": "error", "message": "optional skill unavailable"}})
    rig.behavior[:] = [warning + '\n' + events()]
    assert rig.client.complete("gist", []).text == "answer"
    usage = rig.sink.read_calls()[0]["attempts"][0]["usage"]
    assert usage["codex_startup_warnings"] == ["optional skill unavailable"]


def test_error_during_turn_still_fails_even_if_final_message_follows(rig):
    lines = events().splitlines()
    lines.insert(2, json.dumps({"type": "item.completed", "item": {"type": "error", "message": "turn error"}}))
    rig.behavior[:] = ['\n'.join(lines)]
    with pytest.raises(RuntimeError, match="turn error"):
        rig.client.complete("gist", [])


@pytest.mark.parametrize("output", ["not json", events(text=""),
    json.dumps({"type": "turn.failed", "error": {"message": "quota exhausted"}}),
    events() + '\n' + json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": "cat hidden"}})])
def test_invalid_failed_or_tool_using_cli_never_becomes_success(rig, output):
    rig.behavior[:] = [output]
    with pytest.raises(RuntimeError):
        rig.client.complete("gist", [])
    assert rig.summary()["counts"]["failed"] == 1


def test_non_chatgpt_auth_is_local_failure_and_never_launches_model(rig, monkeypatch):
    monkeypatch.setattr(rig.module.subprocess, "run", lambda *args, **kwargs:
        SimpleNamespace(returncode=0, stdout="Logged in using an API key", stderr=""))
    with pytest.raises(RuntimeError, match="ChatGPT"):
        rig.client.complete("gist", [])
    assert rig.calls == [] and rig.summary()["attempts"] == 0
    assert rig.summary()["calls_by_status"]["local_failed"] == 1


def test_timeout_reaps_process_group_and_preserves_unknown_cost(rig, monkeypatch):
    import subprocess
    killed = []
    rig.behavior[:] = [subprocess.TimeoutExpired("codex", 1)]
    monkeypatch.setattr(rig.module.os, "killpg", lambda *args: killed.append(args))
    with pytest.raises(RuntimeError, match="超时"):
        rig.client.complete("gist", [])
    assert killed and rig.summary()["unknown_cost_attempts"] == 1


def test_cli_error_can_fallback_to_existing_litellm(rig, monkeypatch):
    rig.config.roles["gist"].fallbacks = ["test/backup"]
    rig.behavior[:] = [json.dumps({"type": "turn.failed", "error": {"message": "unavailable"}})]
    monkeypatch.setattr("alienqa.llm.client._litellm", lambda: SimpleNamespace(completion=lambda **kwargs:
        {"choices": [{"message": {"content": "backup"}}], "usage": {"total_tokens": 3}}))
    assert rig.client.complete("gist", []).text == "backup"
    assert [a["model"] for a in rig.sink.read_calls()[0]["attempts"]] == ["codex/gpt-6.1-sol", "test/backup"]


def test_ui_codex_settings_do_not_request_or_store_an_api_key(tmp_path):
    from alienqa.ui import create_ui_app
    app = create_ui_app("config/codex.yaml", settings_path=str(tmp_path / "settings.yaml"), runs_dir=str(tmp_path / "runs"))
    client = app.test_client()
    html = client.get("/settings").get_data(as_text=True)
    assert "codex login" in html and 'name="key_codex"' not in html
    assert client.post("/settings", data={"key_codex": "never-save-as-api-key"}).status_code == 200
    assert "codex" not in app.config["store"].load().llm_keys


def test_judge_advertised_example_matches_parser_and_versions_new_prompt(rig):
    """The advertised mismatch shape must satisfy the actual consumer contract."""
    from alienqa.llm import LlmRoles
    from alienqa.expectation.models import parse_judgment
    rig.behavior[:] = [events('{"status":"passed","mismatches":[]}')]
    LlmRoles(rig.client).judge("保存", '[{"expectation_id":"EX-1","text":"应有反馈"}]', b"a", b"b", repair=True)
    prompt = rig.calls[0].input
    example = json.loads(prompt.split("输出形状示例：\n", 1)[1].split('\n', 1)[0])
    result = parse_judgment(json.dumps(example))
    assert result.status == "mismatch" and result.mismatches[0].expectation_id
    assert isinstance(example['mismatches'][0]['expectation'], str)
    assert "不得把 ID 拼进 expectation" in prompt
    assert rig.sink.read_calls()[0]["prompt_version"] == "judgment-v2"
