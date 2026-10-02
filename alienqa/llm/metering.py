"""Run-local request ledger. Unknown usage/cost is never converted to zero."""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import math
import os
import re
import threading
import uuid

from ..driver.runtime import clean_message
from ..persistence import atomic_write_json
from ..run_writer import StorageError, read_json

VERSION = 1
STATUSES = {"started", "succeeded", "failed", "unknown", "cancelled"}
CALL_STATUSES = STATUSES | {"local_failed"}
TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")


def now():
    return datetime.now(timezone.utc).isoformat()


def public_text(value, limit=2000):
    text = str(value)
    for key, secret in os.environ.items():
        if (key.endswith("_API_KEY") or key in {"API_KEY", "ACCESS_TOKEN"}) and secret:
            text = text.replace(secret, "[redacted]")
    text = re.sub(r"(?i)(?:authorization\s*[:=]\s*(?:bearer\s+)?|cookies?\s*[:=]\s*)[^\s,;]+", "[redacted]", text)
    return clean_message(text)[:limit]


def public_value(value):
    if isinstance(value, dict):
        return {str(key): public_value(item) for key, item in value.items()
                if not re.search(r"api.?key|authorization|cookies?|storage_state|origins|secret", str(key), re.I)}
    if isinstance(value, (list, tuple)):
        return [public_value(item) for item in value]
    if isinstance(value, str):
        return public_text(value)
    if value is None or type(value) in (bool, int, float):
        return value
    return public_text(value)


def provider_cost(value):
    """Explicit adapter payload only; no unverified library price estimates."""
    if not isinstance(value, dict):
        return None
    try:
        amount = Decimal(str(value["amount"]))
        currency, source = value["currency"], value["source"]
        if not amount.is_finite() or amount < 0 or not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            return None
        if source != "provider_response":
            return None
        return {"amount": str(amount), "currency": currency, "source": source}
    except (KeyError, InvalidOperation, ValueError):
        return None


class MeteringSink:
    def __init__(self, directory, run_id):
        self.directory = Path(directory)
        self.run_id = run_id
        self.lock = threading.RLock()

    def initialize(self, config):
        payload = {"schema_version": VERSION, "run_id": self.run_id,
                   "default_provider": config.default_provider, "request_timeout": config.request_timeout,
                   "roles": {role: {"model": rc.model, "temperature": rc.temperature,
                             "fallbacks": list(rc.fallbacks), "max_tokens": rc.max_tokens} for role, rc in config.roles.items()}}
        if any(rc.model.startswith("codex/") or any(m.startswith("codex/") for m in rc.fallbacks) for rc in config.roles.values()):
            payload["codex"] = {"reasoning_effort": config.codex_reasoning_effort,
                                "harness_version": "alienqa-codex-v1", "authentication": "chatgpt"}
        atomic_write_json(self.directory / "llm" / "config.json", public_value(payload))
        (self.directory / "llm" / "calls").mkdir(parents=True, exist_ok=True)

    def _path(self, call_id):
        if not re.fullmatch(r"[0-9a-f]{32}", call_id):
            raise ValueError("invalid call ID")
        return self.directory / "llm" / "calls" / f"{call_id}.json"

    def _save(self, row):
        for name in ("analysis.html", "report.html"):
            (self.directory / name).unlink(missing_ok=True)
        atomic_write_json(self._path(row["call_id"]), row)

    def start_call(self, role, context, *, purpose="complete", messages=None):
        call_id = uuid.uuid4().hex
        relative = f"llm/private/{call_id}-input.json"
        # Private files keep bounded, credential-cleaned text, never image bytes.
        private = {"messages": _private_messages(messages or [])}
        atomic_write_json(self.directory / relative, private)
        row = {"schema_version": VERSION, "run_id": self.run_id, "call_id": call_id,
               "role": role, "step_id": context.get("step_id"), "action_id": context.get("action_id"),
               "phase": context.get("phase", role), "purpose": purpose,
               "parent_call_id": context.get("parent_call_id"), "sample_index": context.get("sample_index"),
               "prompt_version": context.get("prompt_version", "roles-v1"),
               "input_ref": context.get("input_ref") or relative, "private_input_ref": relative,
               "output_ref": None, "started_at": now(), "finished_at": None, "status": "started",
               "parse_status": "not_checked", "attempts": []}
        with self.lock:
            self._save(public_value(row))
        return call_id

    def start_attempt(self, call_id, model, config):
        with self.lock:
            row = read_json(self._path(call_id))
            index = len(row["attempts"]) + 1
            row["attempts"].append({"attempt_index": index, "model": public_text(model),
                "status": "started", "started_at": now(), "finished_at": None,
                "elapsed_seconds": None, "config": public_value(config), "usage": None, "cost": None})
            self._save(row)
            return index

    def local_error(self, call_id, model, error):
        with self.lock:
            row = read_json(self._path(call_id))
            row.setdefault("local_errors", []).append({"model": public_text(model), "error_type": type(error).__name__,
                                                        "error": public_text(error)})
            self._save(row)

    def finish_attempt(self, call_id, index, *, status, elapsed_seconds, usage=None, cost=None, error=None, response_error=None):
        with self.lock:
            row = read_json(self._path(call_id))
            row["attempts"][index - 1].update(status=status, finished_at=now(), elapsed_seconds=elapsed_seconds,
                usage=public_value(usage), cost=provider_cost(cost), error=public_text(error) if error else None,
                response_error=public_text(response_error) if response_error else None,
                error_type=type(error).__name__ if error else None)
            self._save(row)

    def finish_call(self, call_id, status, text=None, error=None):
        with self.lock:
            row = read_json(self._path(call_id))
            if text is not None:
                relative = f"llm/private/{call_id}-output.json"
                atomic_write_json(self.directory / relative, {"text": public_text(text, 16000), "truncated": len(text) > 16000})
                row["output_ref"] = relative
            row.update(status=status, finished_at=now(), error=public_text(error) if error else None)
            self._save(row)

    def mark_parse(self, call_id, status, error=None):
        with self.lock:
            row = read_json(self._path(call_id))
            row.update(parse_status=status, parse_error=public_text(error) if error else None)
            self._save(row)

    def read_calls(self):
        rows = []
        for path in (self.directory / "llm" / "calls").glob("*.json"):
            row = read_json(path)
            if (not isinstance(row, dict) or row.get("schema_version") != VERSION or row.get("run_id") != self.run_id
                    or row.get("call_id") != path.stem or row.get("status") not in CALL_STATUSES
                    or not isinstance(row.get("role"), str) or not isinstance(row.get("attempts"), list)
                    or not isinstance(row.get("started_at"), str)
                    or row.get("parse_status") not in {"not_checked", "not_required", "succeeded", "failed"}):
                raise StorageError(f"{path}: invalid metering schema")
            for index, attempt in enumerate(row["attempts"], 1):
                if (not isinstance(attempt, dict) or attempt.get("status") not in STATUSES
                        or attempt.get("attempt_index") != index or not isinstance(attempt.get("model"), str)
                        or attempt.get("config") is not None and not isinstance(attempt["config"], dict)
                        or attempt.get("usage") is not None and not isinstance(attempt["usage"], dict)
                        or attempt.get("elapsed_seconds") is not None and (type(attempt["elapsed_seconds"]) not in (int, float)
                            or not math.isfinite(attempt["elapsed_seconds"]) or attempt["elapsed_seconds"] < 0)) :
                    raise StorageError(f"{path}: invalid attempt")
            rows.append(row)
        return sorted(rows, key=lambda row: (row["started_at"], row["call_id"]))

    def write_summary(self):
        with self.lock:
            summary = load_summary(self.directory, self.run_id)
            atomic_write_json(self.directory / "usage-summary.json", summary)
        return summary


def _private_messages(messages):
    out = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            content = [{"type": "text", "text": public_text(item.get("text", ""))}
                       if item.get("type") == "text" else {"type": item.get("type"), "content": "image omitted"}
                       for item in content if isinstance(item, dict)]
        else:
            content = public_text(content or "")
        out.append({"role": message.get("role"), "content": content})
    return out


def _aggregate(rows):
    attempts = [attempt for row in rows for attempt in row["attempts"]]
    counts = {status: sum(a["status"] == status for a in attempts) for status in sorted(STATUSES)}
    tokens = {}
    for field in TOKEN_FIELDS:
        values = [(a.get("usage") or {}).get(field) for a in attempts]
        known = [v for v in values if type(v) is int and v >= 0]
        tokens[field] = {"known": sum(known), "unknown_attempts": len(values) - len(known)}
    costs, unknown = {}, 0
    for attempt in attempts:
        cost = provider_cost(attempt.get("cost"))
        if cost is None:
            unknown += 1
            continue
        entry = costs.setdefault(cost["currency"], {"amount": "0", "attempts": 0, "sources": []})
        entry["amount"] = str(Decimal(entry["amount"]) + Decimal(cost["amount"]))
        entry["attempts"] += 1
        if cost["source"] not in entry["sources"]:
            entry["sources"].append(cost["source"])
    elapsed = [a.get("elapsed_seconds") for a in attempts]
    return {"logical_calls": len(rows), "attempts": len(attempts), "counts": counts,
            "attempt_units": dict(Counter((a.get("config") or {}).get("metering_unit", "provider_request") for a in attempts)),
            "calls_by_status": dict(Counter(row["status"] for row in rows)),
            "parse_status": dict(Counter(row.get("parse_status", "not_checked") for row in rows)),
            "tokens": tokens, "known_costs": costs, "unknown_cost_attempts": unknown,
            "elapsed_seconds": sum(v for v in elapsed if type(v) in (int, float)),
            "unknown_duration_attempts": sum(v is None for v in elapsed)}


def load_summary(directory, run_id):
    directory = Path(directory)
    base = {"schema_version": VERSION, "run_id": run_id, "hard_cost_limit": False,
            "notice": "仅有动作/时间预算；费用缺失与未完成请求为未知，停止本地任务不保证供应商停止计费。"}
    try:
        rows = MeteringSink(directory, run_id).read_calls()
        config_path = directory / "llm" / "config.json"
        config = read_json(config_path) if config_path.exists() else None
        if config is not None and (not isinstance(config, dict) or config.get("schema_version") != VERSION
                                  or config.get("run_id") != run_id or not isinstance(config.get("roles"), dict)):
            raise StorageError(f"{config_path}: invalid configuration")
        exists = (directory / "llm" / "calls").is_dir()
        errors = read_json(directory / "llm" / "metering-errors.json") if (directory / "llm" / "metering-errors.json").exists() else []
        if not isinstance(errors, list):
            raise StorageError("invalid metering errors")
        result = {**base, **_aggregate(rows), "data_status": "storage_failed" if errors else "available" if exists else "absent",
                  "errors": errors, "configuration": config, "scan_accounting_recorded": config is not None,
                  "complete": exists and config is not None and not errors
                              and not any(r["status"] in {"started", "unknown"} or any(a["status"] in {"started", "unknown"}
                                          for a in r["attempts"]) for r in rows)}
        result["by_role"] = {role: _aggregate([r for r in rows if r["role"] == role]) for role in sorted({r["role"] for r in rows})}
        result["by_model"] = {model: _aggregate([{**r, "attempts": [a for a in r["attempts"] if a["model"] == model]}
                            for r in rows if any(a["model"] == model for a in r["attempts"])])
                            for model in sorted({a["model"] for r in rows for a in r["attempts"]})}
        if result["attempt_units"].get("cli_invocation"):
            result["notice"] += " Codex attempts 计数为 CLI 启动次数，未直接观察供应商 HTTP 请求；订阅额度消耗不等于零费用。"
        return result
    except (OSError, TypeError, ValueError, KeyError) as exc:
        return {**base, "data_status": "corrupt", "complete": False, "error": public_text(exc)}


def close_unfinished(directory, run_id, termination):
    sink = MeteringSink(directory, run_id)
    with sink.lock:
        for row in sink.read_calls():
            changed = False
            if row["status"] == "started":
                row.update(status="unknown", termination=termination, finished_at=None)
                changed = True
            for attempt in row["attempts"]:
                if attempt["status"] == "started":
                    attempt.update(status="unknown", termination=termination)
                    changed = True
            if changed:
                sink._save(row)
        return sink.write_summary()
