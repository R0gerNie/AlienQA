"""AlienQA 用户前端：Flask 控制台（运行扫描 / 密钥设置 / 历史浏览 / 磁盘目录浏览）。"""
from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import ascii_uppercase

from flask import Flask, jsonify, render_template, request, send_file

from ..llm import LLMClient, load_config
from ..loader import EntryDetector, Project, VisibleFile
from ..pipeline import AlienQAPipeline
from ..review import Decision, ReportBuilder
from .runs import RunManager
from .settings import SettingsStore, providers_from_config


def list_directory(path: str) -> dict:
    """磁盘目录浏览：空路径列出盘符；否则列出子项（目录在前）。"""
    if not path:
        entries = [
            {"name": f"{d}:\\", "path": f"{d}:\\", "is_dir": True}
            for d in ascii_uppercase
            if Path(f"{d}:\\").exists()
        ]
        return {"path": "", "parent": None, "entries": entries}

    p = Path(path)
    if not p.exists() or not p.is_dir():
        return {"path": str(p), "parent": _parent(p), "entries": []}
    try:
        children = sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))
        entries = [{"name": c.name, "path": str(c), "is_dir": c.is_dir()} for c in children]
    except PermissionError:
        entries = []
    return {"path": str(p), "parent": _parent(p), "entries": entries}


def _parent(p: Path) -> str | None:
    if p.parent == p:
        return None
    return str(p.parent)


def _sorted_evidences(evidences: list, by: str = "severity") -> list:
    if by == "alphabetical":
        return sorted(evidences, key=lambda e: e.id)
    order = {"critical": 0, "major": 1, "minor": 2, "trivial": 3}
    return sorted(evidences, key=lambda e: order.get(e.severity.value, 9))


def _serve(directory: str) -> tuple:
    """起一个本地静态服务器，返回 (server, base_url)。"""

    class _Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D401
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(directory)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def create_ui_app(config_path: str, settings_path: str | None = None, runs_dir: str | None = None) -> Flask:
    config = load_config(config_path)
    store = SettingsStore(settings_path or "config.local.yaml")
    settings = store.load()
    runs = RunManager(runs_dir or "runs")
    providers = providers_from_config(config)

    app = Flask(__name__)
    app.config["config"] = config
    app.config["store"] = store
    app.config["settings"] = settings
    app.config["runs"] = runs
    app.config["providers"] = providers
    app.config["report_builder"] = ReportBuilder(LLMClient(config))
    app.config["entry_detector"] = EntryDetector(LLMClient(config))
    app.config["jobs"] = {}
    app.config["running"] = False

    @app.route("/")
    def index():
        return render_template("index.html", active="run", settings=settings,
                               providers=providers, recent=runs.list()[:10])

    @app.route("/settings", methods=["GET", "POST"])
    def settings_page():
        if request.method == "POST":
            keys = {}
            for provider in providers:
                value = (request.form.get(f"key_{provider}") or "").strip()
                if value:
                    keys[provider] = value
            settings.llm_keys = keys
            settings.project_path = (request.form.get("project_path") or "").strip()
            settings.unit = (request.form.get("unit") or "").strip()
            settings.instructions = (request.form.get("instructions") or "").strip()
            store.save(settings)
            return render_template("settings.html", active="settings", saved=True,
                                   settings=settings, providers=providers)
        return render_template("settings.html", active="settings", saved=False,
                               settings=settings, providers=providers)

    @app.route("/api/browse")
    def api_browse():
        return jsonify(list_directory(request.args.get("path", "")))

    @app.route("/api/run", methods=["POST"])
    def api_run():
        if app.config["running"]:
            return jsonify({"error": "已有扫描进行中，请稍候"}), 409
        data = request.get_json(force=True)
        project_path = (data.get("project_path") or "").strip()
        unit = (data.get("unit") or "").strip()
        instructions = (data.get("instructions") or "").strip()
        if not project_path:
            return jsonify({"error": "缺少项目路径"}), 400
        if not Path(project_path).is_dir():
            return jsonify({"error": f"目录不存在：{project_path}"}), 400
        settings.project_path = project_path
        settings.unit = unit
        settings.instructions = instructions
        store.save(settings)
        # 01+ 智能识别入口文件（全局 / 按单元语义）
        entry = app.config["entry_detector"].detect(project_path, unit, instructions)
        rec = runs.create(project_path, unit, entry, instructions)
        _start_job(app, rec, project_path, entry)
        return jsonify({"run_id": rec.id})

    @app.route("/api/run/<run_id>")
    def api_run_status(run_id):
        rec = runs.get(run_id)
        if rec is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(rec.to_dict())

    @app.route("/history")
    def history():
        return render_template("history.html", active="history", runs=runs.list())

    @app.route("/runs/<run_id>")
    def run_detail(run_id):
        rec = runs.get(run_id)
        if rec is None:
            return "未找到该扫描", 404
        report_exists = (rec.dir / "report.html").exists()
        review_ready = (rec.dir / "evidences.json").exists()
        scope = runs.load_scope(run_id)
        return render_template("run.html", active="run", rec=rec,
                               report_exists=report_exists, review_ready=review_ready, scope=scope)

    @app.route("/runs/<run_id>/review")
    def run_review(run_id):
        rec = runs.get(run_id)
        if rec is None:
            return "未找到该扫描", 404
        evidences = runs.load_evidences(run_id)
        state = runs.load_review(run_id)
        by = request.args.get("sort", "severity")
        rows = [
            {
                "id": e.id,
                "severity": e.severity.value,
                "expectation": e.expectation,
                "accepted": state.decision(e.id) == Decision.CONFIRMED,
                "decision": state.decision(e.id).value,
            }
            for e in _sorted_evidences(evidences, by)
        ]
        return render_template("review.html", active="run", run_id=run_id, rec=rec,
                               rows=rows, sort=by)

    @app.route("/runs/<run_id>/decide", methods=["POST"])
    def run_decide(run_id):
        rec = runs.get(run_id)
        if rec is None:
            return jsonify({"error": "not found"}), 404
        payload = request.get_json(force=True)
        evidence_id = payload.get("evidence_id")
        decision = payload.get("decision")
        if not evidence_id or decision not in ("confirmed", "rejected"):
            return jsonify({"error": "decision 只允许 confirmed/rejected"}), 400
        state = runs.load_review(run_id)
        state.decide(evidence_id, Decision(decision), "")
        runs.save_review(run_id, state)
        return jsonify({"ok": True})

    @app.route("/runs/<run_id>/report")
    def run_report(run_id):
        rec = runs.get(run_id)
        if rec is None:
            return "未找到该扫描", 404
        report = rec.dir / "report.html"
        if not report.exists():
            evidences = runs.load_evidences(run_id)
            state = runs.load_review(run_id)
            investigations = runs.load_investigations(run_id)
            try:
                result = app.config["report_builder"].build(evidences, state, investigations)
            except ValueError as exc:
                return (f"<p>无法生成报告：{exc}</p>"
                        f"<p><a href='/runs/{run_id}/review'>返回审核</a></p>"), 409
            report.write_text(result.html, encoding="utf-8")
        return send_file(report, mimetype="text/html")

    return app


def _start_job(app, rec, project_path: str, entry: str) -> None:
    app.config["running"] = True

    def _job():
        srv = None
        try:
            app.config["settings"].apply_to_env()
            srv, base = _serve(project_path)
            base_url = f"{base}/{entry}"
            project = Project(
                root=project_path,
                framework="Static HTML",
                routes=["/"],
                entry_points=[entry],
                visible_files=[VisibleFile(path=entry, role="page", lines=60)],
                base_url=base_url,
            )
            pipeline = AlienQAPipeline(
                app.config["config"],
                artifacts_dir=str(rec.dir / "artifacts"),
                auto_confirm=False,
                unit=rec.unit,
                instructions=rec.instructions,
                verbose=True,
            )
            result = pipeline.collect(project)
            app.config["runs"].save_results(rec.id, result.evidences, result.investigations)
            app.config["runs"].save_scope(rec.id, result.scope)
            app.config["runs"].finish(
                rec.id, "done",
                evidence_count=len(result.evidences),
                issue_count=len(result.issues),
            )
        except Exception as exc:  # noqa: BLE001
            app.config["runs"].finish(rec.id, "error", error=str(exc))
        finally:
            if srv is not None:
                srv.shutdown()
            app.config["running"] = False

    thread = threading.Thread(target=_job, daemon=True)
    app.config["jobs"][rec.id] = thread
    thread.start()
