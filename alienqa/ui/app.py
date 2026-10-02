"""AlienQA 用户前端：Flask 控制台（运行扫描 / 密钥设置 / 历史浏览 / 磁盘目录浏览）。"""
from __future__ import annotations

import json
from html import escape
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import ascii_uppercase
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request, send_file

from ..local_run import ScanInput, select_project, static_directory, serve_project, source_context, valid_url, validate_config, check_output, check_url, check_browser
from ..llm import LLMClient, load_config
from ..llm.metering import MeteringSink
from ..loader import EntryDetector, ProjectLoader
from ..pipeline import AlienQAPipeline
from ..review import Decision, ReportBuilder
from ..review.service import parse_decision, report_mode, REPORT_FILES, evidence_row, DECISION_LABELS, TERMINAL_STATUSES
from ..persistence import atomic_write_bytes, atomic_write_json
from ..replay import ReplayEngine
from ..run_writer import RunWriter, StorageError, read_json, load_snapshot
from .jobs import JobController
from .runs import RunManager
from .settings import Settings, SettingsStore, providers_from_config

JOB_TIMEOUT_SECONDS = 600


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


def _serve(directory: str, **deployment) -> tuple:
    from ..static_server import serve
    server, base = serve(directory, **deployment)
    return server, base.rstrip('/')


def create_ui_app(config_path: str, settings_path: str | None = None, runs_dir: str | None = None) -> Flask:
    config = load_config(config_path)
    store = SettingsStore(settings_path or "config.local.yaml")
    settings = store.load()
    runs = RunManager(runs_dir or "runs")
    providers = providers_from_config(config)

    app = Flask(__name__)
    app.config["config_path"] = str(Path(config_path).resolve())
    app.config["config"] = config
    app.config["store"] = store
    app.config["settings"] = settings
    app.config["runs"] = runs
    app.config["providers"] = providers
    app.config["report_builder"] = ReportBuilder(LLMClient(config))
    app.config["entry_detector"] = EntryDetector(LLMClient(config))
    app.config["jobs"] = {}
    app.config["running"] = False
    app.config["job_controller"] = JobController()
    app.config["review_lock"] = runs.lock

    @app.route("/")
    def index():
        return render_template("index.html", active="run", settings=settings,
                               providers=providers, recent=runs.list()[:10])

    @app.route("/settings", methods=["GET", "POST"])
    def settings_page():
        if request.method == "POST":
            keys = {}
            for provider in providers:
                if provider == "codex":
                    continue
                value = (request.form.get(f"key_{provider}") or "").strip()
                if value:
                    keys[provider] = value
            settings.llm_keys = keys
            settings.project_path = (request.form.get("project_path") or "").strip()
            settings.base_url = (request.form.get("base_url") or "").strip()
            settings.storage_state = (request.form.get("storage_state") or "").strip()
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
        data = request.get_json(force=True)
        if not isinstance(data, dict):
            return jsonify({"error": "需要 JSON 对象"}), 400
        try:
            inputs = ScanInput.from_dict(data)
            validate_config(config)
            check_output(runs.root)
        except (ValueError, OSError) as exc:
            return jsonify({"error": str(exc)}), 400
        project_path, unit, instructions = inputs.project_path, inputs.unit, inputs.instructions
        mode, base_url, storage_state = inputs.mode, inputs.base_url, inputs.storage_state
        token = app.config["job_controller"].reserve()
        if token is None:
            return jsonify({"error": "已有扫描或重放进行中，请稍候"}), 409
        app.config["running"] = True
        settings.project_path = project_path
        settings.mode = mode
        settings.base_url = base_url
        settings.storage_state = storage_state
        settings.unit = unit
        settings.instructions = instructions
        rec = None
        try:
            store.save(settings)
            rec = runs.create(project_path or base_url, unit, inputs.static_entry, instructions,
                              mode=mode, base_url=base_url, storage_state=storage_state,
                              app_path=inputs.app_path, budget=inputs.budget(), browser=inputs.browser,
                              base_path=inputs.base_path, spa_fallback=inputs.spa_fallback)
            _start_job(app, rec, token)
        except Exception as exc:  # noqa: BLE001
            app.config["job_controller"].release(token)
            app.config["running"] = False
            if rec is not None:
                runs.append_terminal_diagnostic(rec.id, "error", str(exc))
                runs.finish(rec.id, "error", error=str(exc))
            return jsonify({"error": str(exc)}), 500
        return jsonify({"run_id": rec.id})

    @app.route("/api/run/<run_id>/stop", methods=["POST"])
    def api_stop(run_id):
        if runs.get(run_id) is None:
            return jsonify({"error": "not found"}), 404
        if not app.config["job_controller"].cancel(run_id):
            return jsonify({"error": "该任务当前未运行"}), 409
        return jsonify({"status": "cancelling"}), 202

    @app.route("/api/run/<run_id>/replay/<evidence_id>", methods=["POST"])
    def api_replay(run_id, evidence_id):
        with runs.lock:
            rec = runs.get(run_id)
            if rec is None or not any(e.id == evidence_id for e in runs.load_evidences(run_id)):
                return jsonify({"error": "unknown evidence"}), 404
            if rec.status not in TERMINAL_STATUSES:
                return jsonify({"error": "扫描尚未结束，暂时无法重放稳定快照"}), 409
            snapshot = load_snapshot(rec.dir)
            if snapshot is not None and snapshot.get("phase") != "terminal":
                return jsonify({"error": "扫描检查点尚未结束，暂时无法重放稳定快照"}), 409
        token = app.config["job_controller"].reserve()
        if token is None:
            return jsonify({"error": "已有扫描或重放进行中，请稍候"}), 409
        app.config["running"] = True
        try:
            with runs.lock:
                (rec.dir / "replay_completions" / f"{evidence_id}.json").unlink(missing_ok=True)
                (rec.dir / "replay_progress" / f"{evidence_id}.json").unlink(missing_ok=True)
                runs.save_replay_result(run_id, evidence_id, {"evidence_id": evidence_id, "status": "running"})
            app.config["job_controller"].start(
                token, run_id, _replay_worker, (str(runs.root), run_id, evidence_id),
                lambda failure: _complete_replay(app, run_id, evidence_id, failure), JOB_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            app.config["job_controller"].release(token)
            _complete_replay(app, run_id, evidence_id, "error")
            return jsonify({"error": str(exc)}), 500
        return jsonify({"run_id": run_id, "evidence_id": evidence_id}), 202

    @app.route("/api/run/<run_id>/replays")
    def api_replays(run_id):
        if runs.get(run_id) is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(runs.load_replay_results(run_id))

    @app.route("/api/run/<run_id>")
    def api_run_status(run_id):
        rec = runs.get(run_id)
        if rec is None:
            return jsonify({"error": "not found"}), 404
        progress = runs.summary(run_id)
        metadata = rec.to_dict()
        if progress.get("data_status") == "available":
            metadata.update(evidence_count=progress["evidence_count"], issue_count=progress["issue_count"],
                            accepted_count=progress["confirmed"])
        return jsonify({**metadata, "progress": progress})

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
        try:
            scope = runs.load_scope(run_id)
        except StorageError:
            scope = None  # load_diagnostics below exposes the actual read failure
        diagnostics = runs.load_diagnostics(run_id)
        return render_template("run.html", active="run", rec=rec,
                               report_exists=report_exists, analysis_exists=(rec.dir / "analysis.html").exists(),
                               review_ready=review_ready, scope=scope,
                               diagnostics=diagnostics, usage=runs.load_usage(run_id), progress=runs.summary(run_id))

    @app.route("/runs/<run_id>/review")
    def run_review(run_id):
        rec = runs.get(run_id)
        if rec is None:
            return "未找到该扫描", 404
        with runs.lock:
            evidences = runs.load_evidences(run_id)
            state = runs.load_review(run_id)
            by = request.args.get("sort", "severity")
            replays = runs.load_replay_results(run_id)
            rows = [{**evidence_row(e, state, rec.dir), "replay": replays.get(e.id)} for e in _sorted_evidences(evidences, by)]
        return render_template("review.html", active="run", run_id=run_id, rec=rec,
                               rows=rows, sort=by, decision_labels=DECISION_LABELS)

    @app.route("/runs/<run_id>/decide", methods=["POST"])
    def run_decide(run_id):
        try:
            evidence_id, decision, note = parse_decision(request.get_json(silent=True))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        try:
            with runs.lock:
                if runs.get(run_id) is None:
                    return jsonify({"error": "未找到该扫描"}), 404
                if not any(e.id == evidence_id for e in runs.load_evidences(run_id)):
                    return jsonify({"error": "证据不存在"}), 404
                state = runs.load_review(run_id)
                state.decide(evidence_id, decision, note)
                runs.save_review(run_id, state)
        except StorageError:
            raise
        except OSError as exc:
            return jsonify({"error": f"保存决定失败：{exc}"}), 500
        return jsonify({"ok": True, "evidence_id": evidence_id, "decision": decision.value, "note": note})

    @app.route("/runs/<run_id>/report")
    def run_report(run_id):
        try:
            mode = report_mode(request.args.get("mode", "confirmed"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        try:
            with runs.lock:
                rec = runs.get(run_id)
                if rec is None:
                    return "未找到该扫描", 404
                snapshot = runs.load_report_snapshot(run_id)
                builder = app.config["report_builder"]
                if mode == "confirmed":
                    builder._validate(snapshot["evidences"], snapshot["state"])
                path = rec.dir / REPORT_FILES[mode]
                if not path.exists() or runs.load_usage(run_id).get("data_status") in {"corrupt", "storage_failed"}:
                    result = builder.build(**snapshot, mode=mode)
                    atomic_write_bytes(path, result.html.encode("utf-8"))
                return send_file(path.resolve(), mimetype="text/html", as_attachment=request.args.get("download") == "1",
                                 download_name=REPORT_FILES[mode], max_age=0)
        except StorageError:
            raise
        except ValueError as exc:
            return (f"<p>无法生成报告：{escape(str(exc))}</p>"
                    f"<p><a href='/runs/{escape(run_id, quote=True)}/report?mode=analysis'>查看 QA 与用户认知分析</a> · "
                    f"<a href='/runs/{escape(run_id, quote=True)}/review'>返回审核</a></p>"), 409
        except OSError as exc:
            return jsonify({"error": f"保存报告失败：{exc}"}), 500

    @app.errorhandler(StorageError)
    def storage_error(error):
        if request.path.startswith("/api/") or request.path.endswith("/decide"):
            return jsonify({"error": str(error), "data_status": error.status}), 409
        return str(error), 409, {"Content-Type": "text/plain; charset=utf-8"}

    return app


# Backward-compatible helper names used by local callers.
_valid_url = valid_url
_static_directory = static_directory


def _prepare_project(rec, detector):
    loader = ProjectLoader()
    if rec.mode == "browser":
        return loader.load_browser(rec.base_url, storage_state=rec.storage_state), None
    project = select_project(loader, rec.project_path, rec.app_path)
    project.storage_state = rec.storage_state
    if rec.base_url:
        project.base_url = rec.base_url
        project.environment["base_url_status"] = "explicit_url"
        return project, None
    server, entry = serve_project(project, rec.entry, rec.base_path, rec.spa_fallback)
    rec.entry = entry
    return project, server


def _start_job(app, rec, token: str) -> None:
    app.config["job_controller"].start(
        token, rec.id, _scan_worker,
        (str(app.config["config_path"]), app.config["settings"].to_dict(), str(app.config["runs"].root), rec.id),
        lambda failure: _complete_scan(app, rec.id, failure), JOB_TIMEOUT_SECONDS,
    )


def _scan_worker(config_path: str, settings_data: dict, runs_dir: str, run_id: str) -> None:
    """Everything that may wait on LLM/browser runs inside the child process."""
    runs = RunManager(runs_dir)
    rec = runs.get(run_id)
    if rec is None:
        raise ValueError("run not found")
    server = None
    completion = {}
    try:
        Settings.from_dict(settings_data).apply_to_env()
        config = load_config(config_path)
        validate_config(config)
        check_output(rec.dir)
        check_browser(rec.browser)
        preparation_client = LLMClient(config, sink=MeteringSink(rec.dir, run_id))
        preparation_client.set_context(phase="prepare")
        preparation_client._record("initialize", config)
        detector = EntryDetector(preparation_client)
        project, server = _prepare_project(rec, detector)
        check_url(project.base_url)
        runs.update_target(run_id, rec.entry or project.base_url, project.base_url, source_context(project))
        pipeline = AlienQAPipeline(config, artifacts_dir=str(rec.dir / "artifacts"), auto_confirm=False,
                                   run_dir=rec.dir, run_id=run_id,
                                   unit=rec.unit, instructions=rec.instructions, verbose=True,
                                   browser=rec.browser, **(rec.budget or {}))
        result = pipeline.collect(project)
        # Production collect commits each checkpoint, including terminal. Do not
        # overwrite it with a second in-memory export. Legacy substitutes may save.
        if load_snapshot(rec.dir) is None:
            from dataclasses import asdict, is_dataclass
            RunWriter(rec.dir, run_id).checkpoint(phase="terminal", steps=result.steps, evidences=result.evidences,
                diagnostics=result.diagnostics, investigations=result.investigations, issues=result.issues,
                scope=asdict(result.scope) if is_dataclass(result.scope) else result.scope,
                raw_refs=getattr(result, "raw_refs", []), stop_reason=getattr(result, "stop_reason", ""),
                access_result=getattr(result, "access_result", None))
        completion = {"status": "partial" if result.incomplete else "done",
                      "evidence_count": len(result.evidences), "issue_count": len(result.issues)}
    except Exception as exc:  # noqa: BLE001
        try:
            runs.append_terminal_diagnostic(run_id, "error", str(exc), component="scan")
        except OSError:
            pass  # completion/error is separate; never overwrite a corrupt or unwritable prefix
        completion = {"status": "error", "error": str(exc)}
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        runs._write_json(rec.dir / "completion.json", completion)


def _complete_scan(app, run_id: str, failure: str | None) -> None:
    runs = app.config["runs"]
    with runs.lock:
        rec = runs.get(run_id)
        if rec is None or rec.status != "running":
            app.config["running"] = bool(rec and rec.status == "cleanup_failed")
            return
        message = ""
        status = failure
        try:
            if failure == "cleanup_failed":
                message = "未能确认任务与子进程退出，保留并发锁"
                runs.finish(run_id, failure, error=message)
                app.config["running"] = True
                return  # a worker may still own its files
            if failure:
                message = {"timeout": "扫描超时，任务与浏览器已停止", "cancelled": "用户停止了扫描，任务与浏览器已停止",
                           "error": "扫描进程异常退出"}.get(failure, failure)
                saved = runs.append_terminal_diagnostic(run_id, failure, message)
            else:
                completion = read_json(rec.dir / "completion.json")
                if not isinstance(completion, dict) or completion.get("status") not in {"done", "partial", "error"}:
                    raise StorageError("completion.json: invalid completion")
                saved = load_snapshot(rec.dir)
                if saved is None or saved["run_id"] != run_id or saved["phase"] != "terminal":
                    raise StorageError("worker exited without a matching terminal checkpoint")
                status = "error" if completion["status"] == "error" else "partial" if saved["incomplete"] else "done"
                message = completion.get("error", "") if status == "error" else ""
            runs.finish(run_id, status, evidence_count=len(saved["evidences"]),
                        issue_count=len(saved.get("issues", [])), error=message)
        except OSError as exc:
            message = str(exc)
            try:
                saved = runs.append_terminal_diagnostic(run_id, failure or "error", message)
                runs.finish(run_id, failure or "error", evidence_count=len(saved["evidences"]),
                            issue_count=len(saved.get("issues", [])), error=message)
            except OSError:
                runs.finish(run_id, failure or "error", error=message)
        finally:
            if failure != "cleanup_failed":
                try:
                    runs.finish_usage(run_id, runs.get(run_id).status)
                except OSError:
                    pass
                app.config["running"] = False


def _replay_worker(runs_dir: str, run_id: str, evidence_id: str) -> None:
    runs = RunManager(runs_dir)
    rec = runs.get(run_id)
    try:
        progress_path = rec.dir / "replay_progress" / f"{evidence_id}.json"
        result = ReplayEngine(replay_dir=str(rec.dir / "artifacts" / "replay"),
                              on_progress=lambda payload: atomic_write_json(progress_path, payload)).replay(evidence_id)
        payload = result.to_dict(include_replay=False)
    except Exception as exc:  # noqa: BLE001
        payload = {"evidence_id": evidence_id, "status": "failed", "reproduced": False, "note": str(exc)}
    atomic_write_json(rec.dir / "replay_completions" / f"{evidence_id}.json", payload)


def _complete_replay(app, run_id: str, evidence_id: str, failure: str | None) -> None:
    runs = app.config["runs"]
    with runs.lock:
        rec = runs.get(run_id)
        if rec is None:
            app.config["running"] = failure == "cleanup_failed"
            return
        path = rec.dir / "replay_completions" / f"{evidence_id}.json"
        try:
            progress = rec.dir / "replay_progress" / f"{evidence_id}.json"
            result = read_json(path) if path.exists() else read_json(progress) if progress.exists() else runs.load_replay_results(run_id).get(evidence_id, {})
            if not isinstance(result, dict):
                raise StorageError(f"{path}: invalid replay completion")
        except StorageError as exc:
            result = {"evidence_id": evidence_id, "status": "failed", "reproduced": False, "note": str(exc)}
        if failure is not None or result.get("status") == "running" or not result:
            result = {**result, "evidence_id": evidence_id, "status": "inconclusive" if failure in {"timeout", "cancelled"} else "failed",
                      "termination": failure, "reproduced": False,
                      "note": "重放已停止，目标是否再现未知" if failure in {"timeout", "cancelled"} else "重放进程未完成"}
        try:
            runs.save_replay_result(run_id, evidence_id, result)
            path.unlink(missing_ok=True)
        finally:
            app.config["running"] = failure == "cleanup_failed"
