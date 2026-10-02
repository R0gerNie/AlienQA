"""Standalone developer review with the same decisions and report semantics."""
from pathlib import Path
import threading

from flask import Flask, Response, jsonify, render_template, request, send_file

from ..persistence import atomic_write_bytes
from ..run_writer import StorageError
from .models import ReviewState
from .report import ReportBuilder
from .service import (HumanReview, DECISION_LABELS, REPORT_FILES, TERMINAL_STATUSES,
                      evidence_row, invalidate_report_paths, parse_decision, report_mode)


def create_app(review: HumanReview, report_builder: ReportBuilder, investigations=None,
               report_path=None, review_path=None, *, scan_context=None, report_paths=None) -> Flask:
    app = Flask(__name__)
    # Existing embedding API represents completed evidence supplied by its caller.
    context = scan_context if scan_context is not None else {"status": "done", "data_status": "legacy；范围及完整性未记录"}
    directory = context.get("run_dir") or (str(Path(report_path).parent) if report_path else None)
    paths = {mode: Path(directory) / name for mode, name in REPORT_FILES.items()} if directory else {}
    if report_path:
        paths["confirmed"] = Path(report_path)
    if report_paths:
        paths.update({report_mode(mode): Path(path) for mode, path in report_paths.items()})
    if len({path.resolve() for path in paths.values()}) != len(paths):
        raise ValueError("两种报告必须使用不同路径")
    app.config.update(review=review, report_builder=report_builder, evidences=[],
                      investigations=list(investigations or []), report_path=report_path,
                      report_paths=paths, review_path=review_path, diagnostics=[], scan_context=context,
                      review_lock=threading.RLock())

    def current_state():
        path = app.config["review_path"]
        return HumanReview.load(path).state if path and Path(path).exists() else review.state

    def invalidate():
        invalidate_report_paths(app.config["report_paths"].values())

    @app.route("/")
    def index():
        with app.config["review_lock"]:
            state = current_state()
            by = request.args.get("sort", "severity")
            rows = [evidence_row(e, state, app.config["scan_context"].get("run_dir")) for e in review.sorted_evidences(app.config["evidences"], by)]
        return render_template("inbox.html", rows=rows, sort=by, decision_labels=DECISION_LABELS)

    @app.route("/decide", methods=["POST"])
    def decide():
        try:
            evidence_id, decision, note = parse_decision(request.get_json(silent=True))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        try:
            with app.config["review_lock"]:
                if not any(e.id == evidence_id for e in app.config["evidences"]):
                    return jsonify({"error": "证据不存在"}), 404
                state = ReviewState.from_dict(current_state().to_dict())
                state.decide(evidence_id, decision, note)
                # Pre-invalidation prevents a deletion failure from leaving stale
                # HTML next to successfully updated decisions. Invalidate again after save.
                invalidate()
                if app.config["review_path"]:
                    HumanReview(state).save(app.config["review_path"])
                invalidate()
                review.state = state
        except StorageError:
            raise
        except OSError as exc:
            return jsonify({"error": f"保存决定失败：{exc}"}), 500
        return jsonify({"ok": True, "evidence_id": evidence_id, "decision": decision.value, "note": note})

    @app.route("/report")
    def report():
        try:
            mode = report_mode(request.args.get("mode", "confirmed"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        try:
            with app.config["review_lock"]:
                context = app.config["scan_context"]
                if context.get("status") not in TERMINAL_STATUSES:
                    return jsonify({"error": "扫描尚未结束，暂时无法生成报告"}), 409
                result = app.config["report_builder"].build(app.config["evidences"], current_state(),
                    app.config["investigations"], diagnostics=app.config["diagnostics"], mode=mode, scan_context=context)
                path = app.config["report_paths"].get(mode)
                download = request.args.get("download") == "1"
                if path:
                    atomic_write_bytes(path, result.html.encode("utf-8"))
                    return send_file(path.resolve(), mimetype="text/html", as_attachment=download,
                                     download_name=REPORT_FILES[mode], max_age=0)
                response = Response(result.html, mimetype="text/html")
                if download:
                    response.headers["Content-Disposition"] = f'attachment; filename="{REPORT_FILES[mode]}"'
                return response
        except StorageError:
            raise
        except ValueError as exc:
            return jsonify({"error": str(exc), "analysis_url": "/report?mode=analysis"}), 409
        except OSError as exc:
            return jsonify({"error": f"保存报告失败：{exc}"}), 500

    @app.errorhandler(StorageError)
    def storage_error(error):
        return jsonify({"error": str(error), "data_status": error.status}), 409

    return app
