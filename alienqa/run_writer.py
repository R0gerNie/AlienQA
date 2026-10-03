"""Single-writer scan checkpoints. scan.json is the committed authority."""
from copy import deepcopy
import json
from pathlib import Path
import uuid

from .persistence import atomic_write_json
from .cognitive_diagnostics import step_incomplete
from .i18n import normalize_language

SCHEMA_VERSION = 2


class StorageError(OSError):
    def __init__(self, message: str, status: str = "corrupt"):
        super().__init__(message)
        self.status = status


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise StorageError(f"{path}: {exc}") from exc


def load_snapshot(directory: str | Path) -> dict | None:
    directory = Path(directory)
    path = directory / "scan.json"
    if not path.exists():
        marker = directory / "diagnostics.json"
        if marker.exists():
            exported = read_json(marker)
            if isinstance(exported, dict) and exported.get("schema_version") == SCHEMA_VERSION:
                raise StorageError(f"{path}: missing committed checkpoint", "absent")
        return None
    data = read_json(path)
    if not isinstance(data, dict):
        raise StorageError(f"{path}: scan must be an object")
    version = data.get("schema_version")
    if version is None:
        return None
    if version != SCHEMA_VERSION:
        raise StorageError(f"{path}: unsupported schema_version={version}", "unsupported")
    if type(data.get("checkpoint_seq")) is not int or data["checkpoint_seq"] < 1 or not data.get("run_id"):
        raise StorageError(f"{path}: invalid checkpoint identity")
    for field in ("steps", "evidences", "investigations", "diagnostics", "raw_refs"):
        if not isinstance(data.get(field), list) or any(not isinstance(x, dict) for x in data[field]):
            raise StorageError(f"{path}: invalid {field}")
    ids = [e.get("id") for e in data["evidences"]]
    if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise StorageError(f"{path}: invalid evidence IDs")
    records = set()
    for ref in data["raw_refs"]:
        relative = ref.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise StorageError(f"{path}: invalid raw reference")
        raw_path = (directory / relative).resolve()
        if not raw_path.is_relative_to(directory.resolve()):
            raise StorageError(f"{path}: raw reference leaves run directory")
        raw = read_json(raw_path)
        if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
            raise StorageError(f"{raw_path}: invalid raw schema")
        if not isinstance(raw.get("records"), list):
            raise StorageError(f"{raw_path}: invalid raw records")
        actual = [r.get("record_id") for r in raw["records"] if isinstance(r, dict)]
        if (len(actual) != len(raw["records"]) or any(not isinstance(x, str) or not x for x in actual)
                or len(set(actual)) != len(actual) or actual != ref.get("record_ids")):
            raise StorageError(f"{raw_path}: raw record IDs do not match committed reference")
        records.update(actual)
    for e in data["evidences"]:
        source = e.get("source_record_ids", [])
        if not isinstance(source, list) or any(not isinstance(x, str) for x in source) or not set(source).issubset(records):
            raise StorageError(f"{path}: evidence has unknown raw references")
        from .evidence.models import Evidence
        try:
            Evidence.from_dict(e)
        except (ValueError, TypeError) as exc:
            raise StorageError(f"{path}: invalid Evidence: {exc}") from exc
        if e.get("expectation_id"):
            matches = []
            for step in data["steps"]:
                if step.get("step_id") != e.get("step_id") or step.get("action_id") != e.get("action_id"):
                    continue
                rows = step.get("expectations", [])
                if isinstance(rows, list):
                    matches.extend(row for row in rows if isinstance(row, dict) and row.get("id") == e["expectation_id"])
            if (e.get("finding_kind") != "cognitive_mismatch" or len(matches) != 1
                    or e.get("run_id") != data["run_id"]
                    or any(matches[0].get(key) != e.get(key) for key in ("run_id", "step_id", "action_id"))
                    or matches[0].get("text") != e.get("expectation")
                    or matches[0].get("expectation_basis") != e.get("expectation_basis")):
                raise StorageError(f"{path}: invalid committed expectation reference")
    return data


class RunWriter:
    def __init__(self, directory: str | Path, run_id: str | None = None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        saved = load_snapshot(self.directory)
        self.run_id = run_id or (saved or {}).get("run_id") or uuid.uuid4().hex
        if saved and saved["run_id"] != self.run_id:
            raise StorageError("run directory belongs to another run")
        self.seq = (saved or {}).get("checkpoint_seq", 0)
        self.last_stage = (saved or {}).get("last_stage") or ((saved or {}).get("phase") if (saved or {}).get("phase") != "terminal" else None)

    def save_raw(self, payload: dict, *, phase: str) -> dict:
        relative = f"raw/{uuid.uuid4().hex}.json"
        data = {**payload, "schema_version": SCHEMA_VERSION, "run_id": self.run_id, "phase": phase}
        try:
            atomic_write_json(self.directory / relative, data)
        except OSError as exc:
            raise StorageError(f"raw storage_failed: {exc}", "storage_failed") from exc
        return {"path": relative, "record_ids": [r["record_id"] for r in payload["records"]],
                "window": payload.get("window", {}), "phase": phase}

    def checkpoint(self, *, phase: str, steps: list, evidences: list, diagnostics: list,
                   raw_refs: list | None = None, investigations: list | None = None,
                   stop_reason: str = "", scope=None, issues: list | None = None, access_result: dict | None = None,
                   language: str = 'zh') -> dict:
        def document(value):
            return value.to_dict() if hasattr(value, "to_dict") else value

        payload = deepcopy({"schema_version": SCHEMA_VERSION, "run_id": self.run_id,
                            "checkpoint_seq": self.seq + 1, "phase": phase,
                            "last_stage": self.last_stage if phase == "terminal" else phase,
                            "steps": steps, "evidences": [document(e) for e in evidences],
                            "investigations": [document(i) for i in investigations or []],
                            "diagnostics": diagnostics, "raw_refs": raw_refs or [],
                            "scope": scope, "stop_reason": stop_reason, "access_result": access_result,
                            "language": normalize_language(language),
                            "issues": [document(i) for i in issues or []],
                            "incomplete": phase != "terminal" or bool(diagnostics) or
                            any(step_incomplete(s) for s in steps)})
        # Exports are derived views; scan embeds its own rows so a failed commit
        # cannot change the previous authority through a partly updated export.
        try:
            atomic_write_json(self.directory / "evidences.json", payload["evidences"])
            atomic_write_json(self.directory / "investigations.json", payload["investigations"])
            atomic_write_json(self.directory / "diagnostics.json", {k: payload[k] for k in
                              ("schema_version", "run_id", "checkpoint_seq", "steps", "diagnostics", "incomplete", "stop_reason")})
            if scope is not None:
                atomic_write_json(self.directory / "unit_scope.json", scope)
            atomic_write_json(self.directory / "scan.json", payload)
        except OSError as exc:
            raise StorageError(f"checkpoint storage_failed: {exc}", "storage_failed") from exc
        self.seq += 1
        self.last_stage = payload["last_stage"]
        return payload

    def append_terminal_diagnostic(self, status: str, error: str, component: str = "job",
                                   *, language: str = 'zh') -> dict:
        saved = load_snapshot(self.directory) or {"steps": [], "evidences": [], "diagnostics": [],
                                                  "raw_refs": [], "investigations": [], "issues": []}
        for step in saved["steps"]:
            if step.get("cognitive_status") == "pending":
                step["cognitive_status"] = "inconclusive"
                step["error"] = error
            for phase, value in step.get("phases", {}).items():
                if value == "started":
                    step["phases"][phase] = "incomplete"
            generation = step.get("expectation_generation", {})
            for sample in generation.get("samples", []):
                if sample.get("status") == "started":
                    sample.update(status="incomplete", error=error, error_stage="invocation")
                    if generation.get("sampling"):
                        generation["sampling"]["complete"] = False
        saved["diagnostics"].append({"component": component, "stage": component, "status": status, "error": error})
        return self.checkpoint(phase="terminal", steps=saved["steps"], evidences=saved["evidences"],
                               diagnostics=saved["diagnostics"], raw_refs=saved["raw_refs"],
                               investigations=saved["investigations"], issues=saved["issues"],
                               scope=saved.get("scope"), stop_reason=status, access_result=saved.get("access_result"),
                               language=saved.get("language", language))
