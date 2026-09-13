"""Flask 审核前端：evidence 列表（switcher + 排序）+ 报告页。"""
from flask import Flask, jsonify, render_template, request

from .models import Decision
from .report import ReportBuilder
from .service import HumanReview


def create_app(review: HumanReview, report_builder: ReportBuilder) -> Flask:
    app = Flask(__name__)
    app.config["review"] = review
    app.config["report_builder"] = report_builder
    app.config["evidences"] = []

    @app.route("/")
    def index():
        evidences = app.config["evidences"]
        by = request.args.get("sort", "severity")
        rows = [
            {
                "id": e.id,
                "severity": e.severity.value,
                "expectation": e.expectation,
                "accepted": review.state.decision(e.id) == Decision.CONFIRMED,
                "decision": review.state.decision(e.id).value,
            }
            for e in review.sorted_evidences(evidences, by=by)
        ]
        return render_template("inbox.html", rows=rows, sort=by)

    @app.route("/decide", methods=["POST"])
    def decide():
        payload = request.get_json(force=True)
        evidence_id = payload.get("evidence_id")
        decision = payload.get("decision")  # "confirmed" | "rejected"
        note = payload.get("note", "")
        if not evidence_id or decision not in ("confirmed", "rejected"):
            return jsonify({"error": "decision 只允许 confirmed/rejected"}), 400
        review.decide(evidence_id, Decision(decision), note)
        return jsonify({"ok": True})

    @app.route("/report")
    def report():
        evidences = app.config["evidences"]
        try:
            r = report_builder.build(evidences, review.state)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409
        return r.html

    return app
