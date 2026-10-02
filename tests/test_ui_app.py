"""用户前端 Flask 应用测试（不触发真实 LLM / 扫描）。"""
from alienqa.ui import create_ui_app, list_directory


def _make_app(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  default_provider: openai\n"
        "  request_timeout: 120\n"
        "  roles:\n"
        "    gist:\n"
        "      model: deepseek/deepseek-chat\n"
        "      temperature: 0.1\n"
        "      fallbacks: []\n"
        "    expectation:\n"
        "      model: openai/test\n"
        "    visual:\n"
        "      model: openai/test\n"
        "    judge:\n"
        "      model: dashscope/qwen-vl-plus\n"
        "      temperature: 0.2\n"
        "      fallbacks: []\n"
        "    reporter:\n"
        "      model: deepseek/deepseek-chat\n"
        "      temperature: 0.2\n"
        "      fallbacks: []\n",
        encoding="utf-8",
    )
    return create_ui_app(
        str(cfg),
        settings_path=str(tmp_path / "config.local.yaml"),
        runs_dir=str(tmp_path / "runs"),
    )


def test_index_renders(tmp_path):
    client = _make_app(tmp_path).test_client()
    html = client.get("/").get_data(as_text=True)
    assert "运行扫描" in html
    assert "测试单元" in html
    assert "单元指令" in html
    assert "入口文件" not in html  # 已改为智能识别，不再暴露输入框


def test_history_renders(tmp_path):
    client = _make_app(tmp_path).test_client()
    html = client.get("/history").get_data(as_text=True)
    assert "历史项目" in html


def test_settings_save(tmp_path):
    client = _make_app(tmp_path).test_client()
    r = client.post("/settings", data={
        "key_deepseek": "sk-a",
        "key_dashscope": "sk-b",
        "project_path": "d:/p",
        "unit": "登录页",
    })
    assert r.status_code == 200
    body = (tmp_path / "config.local.yaml").read_text(encoding="utf-8")
    assert "sk-a" in body
    assert "sk-b" in body
    assert "d:/p" in body


def test_api_browse_lists_directory(tmp_path):
    client = _make_app(tmp_path).test_client()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "f.txt").write_text("x", encoding="utf-8")
    data = client.get("/api/browse", query_string={"path": str(tmp_path)}).get_json()
    entries = data["entries"]
    assert entries[0]["name"] == "sub"  # 目录排前
    assert any(e["name"] == "sub" and e["is_dir"] for e in entries)
    assert data["parent"] == str(tmp_path.parent)


def test_api_run_rejects_missing_path(tmp_path):
    client = _make_app(tmp_path).test_client()
    assert client.post("/api/run", json={"project_path": "Z:/no/such/dir"}).status_code == 400


def test_api_run_requires_project_path(tmp_path):
    client = _make_app(tmp_path).test_client()
    assert client.post("/api/run", json={"unit": "x"}).status_code == 400


def test_list_directory_empty_returns_drives():
    data = list_directory("")
    assert isinstance(data["entries"], list)
    assert data["parent"] is None


def test_review_flow(tmp_path):
    from alienqa.evidence import Evidence, Severity
    from alienqa.investigation import Investigation

    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("d:/p", unit="登录页", entry="index.html")
    runs.save_results(
        rec.id,
        [Evidence(id="EV-001", issue_id="ISSUE-001", expectation="点保存应有提示", severity=Severity.MINOR)],
        [Investigation(issue_id="ISSUE-001", root_cause_hypothesis="root")],
    )
    runs.finish(rec.id, "done", evidence_count=1, issue_count=1)
    client = app.test_client()

    html = client.get(f"/runs/{rec.id}/review").get_data(as_text=True)
    assert "EV-001" in html
    assert "<select" in html and "<textarea" in html

    # 未审核 → /report 409（gate 拦截 pending）
    assert client.get(f"/runs/{rec.id}/report").status_code == 409

    # 采信
    r = client.post(f"/runs/{rec.id}/decide", json={"evidence_id": "EV-001", "decision": "confirmed"})
    assert r.status_code == 200
    assert runs.load_review(rec.id).decision("EV-001").value == "confirmed"


def test_url_scan_starts_without_synchronous_entry_detection(tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module("alienqa.ui.app")
    app = _make_app(tmp_path)
    started = []
    monkeypatch.setattr(module, "_start_job", lambda *args: started.append(args))
    monkeypatch.setattr(app.config["entry_detector"], "detect", lambda *args: (_ for _ in ()).throw(AssertionError("synchronous LLM")))
    state = tmp_path / "session.json"
    state.write_text('{"cookies": [], "origins": []}', encoding="utf-8")
    response = app.test_client().post("/api/run", json={
        "mode": "browser", "url": "http://localhost:3000/login", "storage_state": str(state),
    })
    assert response.status_code == 200
    record = app.config["runs"].get(response.get_json()["run_id"])
    assert record.mode == "browser"
    assert record.base_url == "http://localhost:3000/login"
    assert record.storage_state == str(state)
    assert started
    assert app.test_client().post("/api/run", json={"url": "http://localhost:3000"}).status_code == 409


def test_run_rejects_bad_url_and_login_state(tmp_path):
    client = _make_app(tmp_path).test_client()
    assert client.post("/api/run", json={"url": "file:///tmp/index.html"}).status_code == 400
    assert client.post("/api/run", json={"url": "http://localhost:3000", "storage_state": "missing.json"}).status_code == 400


def test_unknown_evidence_cannot_be_reviewed(tmp_path):
    app = _make_app(tmp_path)
    rec = app.config["runs"].create("d:/p")
    response = app.test_client().post(f"/runs/{rec.id}/decide", json={"evidence_id": "EV-missing", "decision": "confirmed"})
    assert response.status_code == 404
    assert not (rec.dir / "review.json").exists()


def test_review_change_invalidates_generated_report(tmp_path):
    from alienqa.evidence import Evidence

    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("d:/p")
    runs.save_results(rec.id, [Evidence(id="EV-001", expectation="save")], [])
    runs.finish(rec.id, "done", evidence_count=1)
    (rec.dir / "report.html").write_text("old report", encoding="utf-8")
    response = app.test_client().post(f"/runs/{rec.id}/decide", json={"evidence_id": "EV-001", "decision": "rejected"})
    assert response.status_code == 200
    assert not (rec.dir / "report.html").exists()


def test_framework_source_requires_running_url(tmp_path, monkeypatch):
    from alienqa.ui.app import _prepare_project
    from alienqa.loader import EntryDetector
    import pytest

    source = tmp_path / "app"
    source.mkdir()
    (source / "package.json").write_text('{"dependencies": {"react": "18", "react-dom": "18"}, "scripts": {"dev": "vite"}}')
    (source / "index.html").write_text('<div id="root"></div><script type="module" src="/src/main.tsx"></script>')
    rec = _make_app(tmp_path).config["runs"].create(str(source))
    with pytest.raises(ValueError, match="URL"):
        _prepare_project(rec, EntryDetector())
    rec.base_url = "http://localhost:5173"
    project, server = _prepare_project(rec, EntryDetector())
    assert project.framework == "React"
    assert project.base_url == rec.base_url
    assert server is None


def test_static_html_is_loaded_and_served(tmp_path):
    from alienqa.ui.app import _prepare_project
    from alienqa.loader import EntryDetector

    source = tmp_path / "static"
    source.mkdir()
    (source / "index.html").write_text("<button>Save</button>")
    rec = _make_app(tmp_path).config["runs"].create(str(source))
    project, server = _prepare_project(rec, EntryDetector())
    try:
        assert project.root == str(source.resolve())
        assert project.base_url.endswith("/index.html")
        assert server is not None
        assert project.artifacts["static_server"]["directory"] == str(source.resolve())
        assert project.artifacts["static_server"]["port"] == server.server_port
        assert project.artifacts["static_server"]["spa_fallback"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_scan_worker_persists_partial_diagnostics(tmp_path, monkeypatch):
    import importlib
    from types import SimpleNamespace

    module = importlib.import_module("alienqa.ui.app")
    app = _make_app(tmp_path)
    rec = app.config["runs"].create("http://localhost:3000", mode="browser", base_url="http://localhost:3000")
    result = SimpleNamespace(evidences=[], investigations=[], scope=None, issues=[], incomplete=True,
                             steps=[{"status": "inconclusive", "error": "missing observation"}],
                             diagnostics=[{"component": "judge", "error": "invalid JSON"}])
    class Pipeline:
        def __init__(self, *args, **kwargs):
            pass
        def collect(self, project):
            return result
    monkeypatch.setattr(module, "AlienQAPipeline", Pipeline)
    monkeypatch.setattr(module, "check_url", lambda url: url)
    monkeypatch.setattr(module, "check_browser", lambda browser: None)
    module._scan_worker(str(tmp_path / "config.yaml"), {}, str(app.config["runs"].root), rec.id)
    diagnostics = app.config["runs"].load_diagnostics(rec.id)
    assert diagnostics["steps"][0]["status"] == "inconclusive"
    assert diagnostics["diagnostics"][0]["component"] == "judge"
    module._complete_scan(app, rec.id, None)
    assert app.config["runs"].get(rec.id).status == "partial"


def test_replay_reuses_busy_slot_and_rejects_unknown_evidence(tmp_path):
    app = _make_app(tmp_path)
    rec = app.config["runs"].create("d:/p")
    client = app.test_client()
    assert client.post(f"/api/run/{rec.id}/replay/EV-missing").status_code == 404


def test_report_is_unavailable_before_scan_finishes(tmp_path):
    app = _make_app(tmp_path)
    rec = app.config["runs"].create("d:/p")
    assert app.test_client().get(f"/runs/{rec.id}/report").status_code == 409
    assert not (rec.dir / "report.html").exists()


def test_partial_report_contains_scan_diagnostics(tmp_path):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("d:/p")
    runs.save_results(rec.id, [], [])
    runs.save_diagnostics(rec.id, [{"status": "inconclusive", "error": "判断资料不足"}],
                          [{"component": "judge", "error": "格式错误"}], True)
    runs.finish(rec.id, "partial")
    response = app.test_client().get(f"/runs/{rec.id}/report")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "格式错误" in html
    assert "判断资料不足" in html


def test_built_frontend_serves_dist_without_source_transformation(tmp_path):
    from alienqa.ui.app import _prepare_project
    from alienqa.loader import EntryDetector

    source = tmp_path / "app"
    source.mkdir()
    (source / "package.json").write_text('{"dependencies": {"react": "18", "react-dom": "18"}}')
    (source / "index.html").write_text('<script src="/src/main.tsx"></script>')
    dist = source / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<script src="/assets/index.js"></script>')
    (dist / "assets").mkdir()
    (dist / "assets/index.js").write_text("console.log('built')")
    rec = _make_app(tmp_path).config["runs"].create(str(source))
    project, server = _prepare_project(rec, EntryDetector())
    try:
        assert project.framework == "React"
        assert server.RequestHandlerClass.keywords["directory"] == str(dist)
    finally:
        server.shutdown()
        server.server_close()


def test_worker_applies_saved_key_before_entry_detector(tmp_path, monkeypatch):
    import importlib
    import os

    module = importlib.import_module("alienqa.ui.app")
    app = _make_app(tmp_path)
    rec = app.config["runs"].create(str(tmp_path))
    seen = []
    def detector(client):
        seen.append(os.environ.get("DEEPSEEK_API_KEY"))
        raise ValueError("stop before model calls")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "old-key")
    monkeypatch.setattr(module, "EntryDetector", detector)
    module._scan_worker(str(tmp_path / "config.yaml"), {"llm_keys": {"deepseek": "new-key"}}, str(app.config["runs"].root), rec.id)
    assert seen == ["new-key"]


def test_replay_shares_task_slot(tmp_path, monkeypatch):
    from alienqa.evidence import Evidence

    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("d:/p")
    runs.save_results(rec.id, [Evidence(id="EV-001")], [])
    replay_dir = rec.dir / "artifacts" / "replay"
    replay_dir.mkdir(parents=True)
    (replay_dir / "EV-001.json").write_text("{}")
    app.config["job_controller"].reserve()
    response = app.test_client().post(f"/api/run/{rec.id}/replay/EV-001")
    assert response.status_code == 409
    assert runs.load_replay_results(rec.id) == {}


def test_replay_worker_does_not_expose_session(tmp_path, monkeypatch):
    import importlib
    from alienqa.replay.models import ReplayResult

    module = importlib.import_module("alienqa.ui.app")
    app = _make_app(tmp_path)
    rec = app.config["runs"].create("d:/p")
    class Engine:
        def __init__(self, **kwargs):
            pass
        def replay(self, evidence_id):
            return ReplayResult(evidence_id=evidence_id, replay={"cookies": [{"value": "secret"}]}, status="inconclusive")
    monkeypatch.setattr(module, "ReplayEngine", Engine)
    module._replay_worker(str(app.config["runs"].root), rec.id, "EV-001")
    assert app.config["runs"].load_replay_results(rec.id) == {}
    module._complete_replay(app, rec.id, "EV-001", None)
    result = app.test_client().get(f"/api/run/{rec.id}/replays").get_json()["EV-001"]
    assert result["status"] == "inconclusive"
    assert "replay" not in result
    assert "secret" not in str(result)


def test_worker_launch_failure_finishes_record_and_releases_slot(tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module("alienqa.ui.app")
    app = _make_app(tmp_path)
    def fail(*args):
        raise OSError("unable to start worker")
    monkeypatch.setattr(module, "_start_job", fail)
    response = app.test_client().post("/api/run", json={"url": "http://localhost:3000"})
    assert response.status_code == 500
    record = app.config["runs"].list()[0]
    assert record.status == "error"
    assert "unable to start worker" in record.error
    assert app.config["job_controller"].reserve() is not None
