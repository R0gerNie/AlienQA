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
    assert "checkbox" in html

    # 未审核 → /report 409（gate 拦截 pending）
    assert client.get(f"/runs/{rec.id}/report").status_code == 409

    # 采信
    r = client.post(f"/runs/{rec.id}/decide", json={"evidence_id": "EV-001", "decision": "confirmed"})
    assert r.status_code == 200
    assert runs.load_review(rec.id).decision("EV-001").value == "confirmed"
