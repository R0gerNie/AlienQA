"""English console and review behavior without model or browser calls."""
import importlib
import re
from types import SimpleNamespace

from alienqa.evidence import Evidence
from alienqa.review import HumanReview, ReportBuilder, create_app
from test_ui_app import _make_app


def test_language_switch_persists_and_keeps_query(tmp_path):
    client = _make_app(tmp_path).test_client()
    assert "运行扫描" in client.get("/").get_data(as_text=True)
    switched = client.get("/language/en?next=/history?sort=alphabetical")
    assert switched.status_code == 302
    assert switched.headers["Location"] == "/history?sort=alphabetical"
    html = client.get("/").get_data(as_text=True)
    assert '<html lang="en">' in html
    assert "Run scan" in html and "Start scan" in html
    assert 'href="/language/zh?' in html
    assert "运行扫描" not in html
    assert "Settings" in client.get("/settings").get_data(as_text=True)


def test_all_console_pages_translate_labels_preserving_evidence(tmp_path):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("http://localhost:3000", unit="用户原文", mode="browser")
    runs.save_results(rec.id, [Evidence(id="EV-1", expectation="保存后反馈")], [])
    runs.finish(rec.id, "done", evidence_count=1)
    client = app.test_client()
    for route in ("/", "/settings", "/history", f"/runs/{rec.id}", f"/runs/{rec.id}/review"):
        html = client.get(route + "?lang=en").get_data(as_text=True)
        assert '<html lang="en">' in html
        # User input remains verbatim; rendered labels and JS strings are English.
        html = html.replace("用户原文", "").replace("保存后反馈", "").replace("中文", "")
        assert re.search(r"[\u4e00-\u9fff]", html) is None, route


def test_english_errors_and_scan_language(tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    module = importlib.import_module("alienqa.ui.app")
    monkeypatch.setattr(module, "_start_job", lambda *args: None)
    client = app.test_client()
    client.get("/language/en?next=/")
    invalid = client.post("/api/run", json=[])
    assert invalid.get_json()["error"] == "A JSON object is required"
    started = client.post("/api/run", json={"mode": "browser", "url": "http://localhost:3000"})
    assert started.status_code == 200
    rec = app.config["runs"].get(started.get_json()["run_id"])
    assert rec.language == "en"
    assert "already" in client.post("/api/run", json={"mode": "browser", "url": "http://localhost:3000"}).get_json()["error"].lower()


def test_report_cache_changes_with_language(tmp_path):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("example")
    runs.save_results(rec.id, [], [])
    runs.finish(rec.id, "done")
    seen = []

    class Builder:
        def _validate(self, *args):
            pass

        def build(self, **kwargs):
            seen.append(kwargs["language"])
            return SimpleNamespace(html=f'<html lang="{kwargs["language"]}"></html>')

    app.config["report_builder"] = Builder()
    client = app.test_client()
    for language in ("zh", "en", "zh"):
        html = client.get(f"/runs/{rec.id}/report?lang={language}").get_data(as_text=True)
        assert f'lang="{language}"' in html
    assert seen == ["zh", "en", "zh"]


def test_console_rebuilds_report_overwritten_by_standalone_review(tmp_path):
    app = _make_app(tmp_path)
    runs = app.config["runs"]
    rec = runs.create("example")
    runs.save_results(rec.id, [], [])
    runs.finish(rec.id, "done")
    seen = []

    class Builder:
        def _validate(self, *args):
            pass

        def build(self, *args, **kwargs):
            seen.append(kwargs["language"])
            return SimpleNamespace(html=f'<html lang="{kwargs["language"]}"></html>')

    builder = Builder()
    app.config["report_builder"] = builder
    client = app.test_client()
    report_url = f"/runs/{rec.id}/report?lang=zh"
    assert 'lang="zh"' in client.get(report_url).get_data(as_text=True)
    standalone = create_app(HumanReview(), builder, report_path=str(rec.dir / "report.html"))
    assert 'lang="en"' in standalone.test_client().get("/report?lang=en").get_data(as_text=True)
    assert 'lang="zh"' in client.get(report_url).get_data(as_text=True)
    assert seen == ["zh", "en", "zh"]
    assert not (rec.dir / "report.html.language").exists()


def test_standalone_review_has_english_switch_and_errors():
    app = create_app(HumanReview(), ReportBuilder(None))
    app.config["evidences"] = [Evidence(id="EV-1", expectation="用户证据")]
    client = app.test_client()
    html = client.get("/?lang=en").get_data(as_text=True)
    assert '<html lang="en">' in html
    assert "Evidence review" in html and "Save decision" in html
    assert "用户证据" in html
    error = client.post("/decide?lang=en", json={"evidence_id": "missing", "decision": "rejected"})
    assert error.status_code == 404
    assert error.get_json()["error"] == "Evidence does not exist"


def test_scan_payload_can_explicitly_select_english(tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    module = importlib.import_module("alienqa.ui.app")
    monkeypatch.setattr(module, "_start_job", lambda *args: None)
    response = app.test_client().post("/api/run", json={
        "mode": "browser", "url": "http://localhost:3000", "language": "en",
    })
    assert response.status_code == 200
    assert app.config["runs"].get(response.get_json()["run_id"]).language == "en"


def test_scan_worker_uses_record_language_in_process_context(tmp_path, monkeypatch):
    from alienqa.i18n import get_language

    app = _make_app(tmp_path)
    module = importlib.import_module("alienqa.ui.app")
    rec = app.config["runs"].create("http://localhost:3000", mode="browser", language="en")
    observed = []

    def detector(client):
        observed.append((client.config.language, get_language()))
        raise ValueError("Stop before model calls")

    monkeypatch.setattr(module, "EntryDetector", detector)
    monkeypatch.setattr(module, "check_browser", lambda browser: None)
    module._scan_worker(str(tmp_path / "config.yaml"), {}, str(app.config["runs"].root), rec.id)
    assert observed == [("en", "en")]
    assert app.config["config"].language == "zh"
    assert get_language() == "zh"
