"""Project-local upstream preparation boundaries, without network installs."""
from pathlib import Path


def test_preparation_keeps_dependency_and_tool_caches_inside_workspace():
    from scripts.prepare_application_suite import WORKSPACE, build_environment
    env = build_environment()
    for key in ("GOPATH", "GOMODCACHE", "GOCACHE", "GOTMPDIR", "TMPDIR", "npm_config_cache",
                "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "TEST_TELEMETRY_DIR"):
        assert Path(env[key]).is_relative_to(WORKSPACE)
    assert env["GOTOOLCHAIN"] == "local" and env["GOENV"] == "off"


def test_upstream_revision_mismatch_stops_without_overwriting_local_checkout(tmp_path, monkeypatch):
    from scripts import prepare_application_suite as preparation
    directory = tmp_path / "checkout"
    directory.mkdir()
    monkeypatch.setattr(preparation.subprocess, "check_output", lambda *a, **k: "other-commit\n")
    monkeypatch.setattr(preparation, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("No reset allowed")))
    import pytest
    with pytest.raises(ValueError, match="revision"):
        preparation.ensure_repository(directory, "https://example.org/repo", "pinned-commit")
