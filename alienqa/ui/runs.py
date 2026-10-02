"""历史扫描目录管理：每次扫描 = 一个目录，元数据写入 run.json。"""
from __future__ import annotations

import json
import re
import time
import threading
from functools import wraps
from dataclasses import dataclass
from pathlib import Path

from ..evidence import Evidence, Severity
from ..persistence import atomic_write_json
from ..run_writer import RunWriter, StorageError, load_snapshot, read_json
from ..investigation import Investigation
from ..review import Decision, ReviewState
from ..llm.metering import load_summary, close_unfinished
from ..review.service import HumanReview, REPORT_FILES, TERMINAL_STATUSES, invalidate_report_paths


def _slug(name: str) -> str:
    name = (name or "project").strip()
    name = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "-", name).strip("-")
    return name or "project"


def _evidence_to_dict(e: Evidence) -> dict:
    return e.to_dict()


def _evidence_from_dict(d: dict) -> Evidence:
    return Evidence.from_dict(d)


@dataclass
class RunRecord:
    """一次扫描的元数据。"""

    id: str
    dir: Path | None = None  # 由 RunManager.get() 回填
    project_path: str = ""
    unit: str = ""
    instructions: str = ""
    entry: str = "index.html"
    mode: str = "source"
    base_url: str = ""
    storage_state: str = ""
    started_at: str = ""
    finished_at: str = ""
    status: str = "running"  # running | done | partial | error | timeout | cancelled | unknown
    evidence_count: int = 0
    issue_count: int = 0
    accepted_count: int = 0
    error: str = ""
    app_path: str = ""
    budget: dict | None = None
    browser: str = "chrome"
    base_path: str = "/"
    spa_fallback: bool = False
    source_context: dict | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_path": self.project_path,
            "unit": self.unit,
            "instructions": self.instructions,
            "entry": self.entry,
            "mode": self.mode,
            "base_url": self.base_url,
            "storage_state": self.storage_state,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "evidence_count": self.evidence_count,
            "issue_count": self.issue_count,
            "accepted_count": self.accepted_count,
            "error": self.error,
            "app_path": self.app_path,
            "budget": self.budget,
            "browser": self.browser,
            "base_path": self.base_path,
            "spa_fallback": self.spa_fallback,
            "source_context": self.source_context,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RunRecord":
        return cls(
            id=str(d.get("id") or ""),
            project_path=str(d.get("project_path") or ""),
            unit=str(d.get("unit") or ""),
            instructions=str(d.get("instructions") or ""),
            entry=str(d.get("entry", "index.html") or ""),
            mode=str(d.get("mode") or "source"),
            base_url=str(d.get("base_url") or ""),
            storage_state=str(d.get("storage_state") or ""),
            started_at=str(d.get("started_at") or ""),
            finished_at=str(d.get("finished_at") or ""),
            status=str(d.get("status") or "unknown"),
            evidence_count=int(d.get("evidence_count") or 0),
            issue_count=int(d.get("issue_count") or 0),
            accepted_count=int(d.get("accepted_count") or 0),
            error=str(d.get("error") or ""),
            app_path=str(d.get("app_path") or ""),
            budget=d.get("budget"),
            browser=str(d.get("browser") or "chrome"),
            base_path=str(d.get("base_path") or "/"),
            spa_fallback=d.get("spa_fallback") is True,
            source_context=d.get("source_context") if isinstance(d.get("source_context"), dict) else None,
        )


def _locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return call


class RunManager:
    """runs_dir 下每个子目录是一次扫描；run.json 记录元数据。"""

    def __init__(self, runs_dir: str | Path):
        self.root = Path(runs_dir)
        self.lock = threading.RLock()

    @_locked
    def create(self, project_path: str, unit: str = "", entry: str = "index.html", instructions: str = "",
               mode: str = "source", base_url: str = "", storage_state: str = "", app_path: str = "", budget: dict | None = None,
               browser: str = "chrome", base_path: str = "/", spa_fallback: bool = False) -> RunRecord:
        run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{_slug(Path(project_path).name)}"
        run_dir = self.root / run_id
        n = 1
        while run_dir.exists():
            run_dir = self.root / f"{run_id}-{n}"
            n += 1
        run_dir.mkdir(parents=True, exist_ok=True)
        rec = RunRecord(
            id=run_dir.name,
            dir=run_dir,
            project_path=project_path,
            unit=unit,
            instructions=instructions,
            entry=entry,
            mode=mode,
            base_url=base_url,
            storage_state=storage_state, app_path=app_path, budget=budget, browser=browser,
            base_path=base_path, spa_fallback=spa_fallback,
            started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            status="running",
        )
        self._write(rec)
        return rec

    @_locked
    def finish(self, run_id: str, status: str, evidence_count: int = 0,
               issue_count: int = 0, accepted_count: int = 0, error: str = "") -> None:
        rec = self.get(run_id)
        if rec is None:
            return
        if rec.status != "running":  # 已被 watchdog 标记 timeout 等，不再回写
            return
        rec.status = status
        rec.evidence_count = evidence_count
        rec.issue_count = issue_count
        rec.accepted_count = accepted_count
        rec.error = error
        rec.finished_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._write(rec)

    def get(self, run_id: str) -> RunRecord | None:
        if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
            return None
        path = self._json_path(run_id)
        if not path.exists():
            return None
        try:
            rec = RunRecord.from_dict(read_json(path))
        except (TypeError, ValueError, AttributeError) as exc:
            raise StorageError(f"{path}: invalid run metadata: {exc}") from exc
        rec.dir = self.root / run_id
        return rec

    def list(self) -> list:
        if not self.root.exists():
            return []
        out = []
        for d in sorted(self.root.iterdir(), key=lambda p: p.name, reverse=True):
            if not d.is_dir():
                continue
            if (d / "run.json").exists():
                try:
                    out.append(self.get(d.name))
                except Exception:  # noqa: BLE001
                    out.append(RunRecord(id=d.name, dir=d, status="error", error="run.json 损坏"))
            else:
                out.append(RunRecord(id=d.name, dir=d, status="unknown"))
        for rec in out:
            try:
                rec.progress = self.summary(rec.id)
            except StorageError as exc:
                rec.progress = {"data_status": exc.status, "error": str(exc)}
        return out

    def _json_path(self, run_id: str) -> Path:
        return self.root / run_id / "run.json"

    # ---- 扫描结果与审核状态持久化 ----

    @_locked
    def save_results(self, run_id: str, evidences: list, investigations: list) -> None:
        rec = self.get(run_id)
        if rec is None:
            return
        self.invalidate_reports(run_id)
        rows, invs = [_evidence_to_dict(e) for e in evidences], [i.to_dict() for i in investigations]
        self._write_json(rec.dir / "evidences.json", rows)
        self._write_json(rec.dir / "investigations.json", invs)
        self._update_checkpoint(rec, evidences=rows, investigations=invs)
        self.invalidate_reports(run_id)

    def load_evidences(self, run_id: str) -> list:
        snapshot = load_snapshot(self.root / run_id)
        if snapshot is not None:
            data = snapshot["evidences"]
        else:
            path = self.root / run_id / "evidences.json"
            data = read_json(path) if path.exists() else []
        try:
            return [_evidence_from_dict(d) for d in data]
        except (TypeError, ValueError) as exc:
            raise StorageError(f"evidences.json: {exc}") from exc

    def load_investigations(self, run_id: str) -> list:
        snapshot = load_snapshot(self.root / run_id)
        if snapshot is not None:
            data = snapshot["investigations"]
        else:
            path = self.root / run_id / "investigations.json"
            data = read_json(path) if path.exists() else []
        return [Investigation.from_dict(d, issue_id=d.get("issue_id", "")) for d in data]

    @_locked
    def save_investigation_result(self, run_id: str, result: Investigation) -> None:
        """Parent-owned optional increment; preserve raw evidence and scan completeness."""
        rec = self.get(run_id)
        if rec is None or rec.status not in TERMINAL_STATUSES:
            raise ValueError("扫描尚未结束，暂时不能更新调查")
        members = {e.id for e in self.load_evidences(run_id) if e.issue_id == result.issue_id}
        if result.evidence_ids and not set(result.evidence_ids).issubset(members):
            raise ValueError("调查成员与当前 Issue 不一致")
        invs = [inv for inv in self.load_investigations(run_id) if inv.issue_id != result.issue_id] + [result]
        self.invalidate_reports(run_id)
        rows = [inv.to_dict() for inv in invs]
        self._write_json(rec.dir / "investigations.json", rows)
        self._update_checkpoint(rec, investigations=rows)
        self.invalidate_reports(run_id)

    @_locked
    def save_review(self, run_id: str, state: ReviewState) -> None:
        rec = self.get(run_id)
        if rec is None:
            return
        self.invalidate_reports(run_id)
        self._write_json(rec.dir / "review.json", state.to_dict())
        self.invalidate_reports(run_id)
        rec.accepted_count = sum(state.decision(e.id) == Decision.CONFIRMED for e in self.load_evidences(run_id))
        self._write(rec)

    def load_review(self, run_id: str) -> ReviewState:
        path = self.root / run_id / "review.json"
        return HumanReview.load(path).state if path.exists() else ReviewState()

    @_locked
    def save_scope(self, run_id: str, scope) -> None:
        """保存单元定位结果（UnitScope）到 unit_scope.json。"""
        rec = self.get(run_id)
        if rec is None or scope is None:
            return
        data = {"unit": getattr(scope, "unit", "") or "", "instructions": getattr(scope, "instructions", "") or "",
                "selectors": list(getattr(scope, "selectors", []) or []), "keywords": list(getattr(scope, "keywords", []) or []),
                "summary": getattr(scope, "summary", "") or ""}
        self.invalidate_reports(run_id)
        self._write_json(rec.dir / "unit_scope.json", data)
        self._update_checkpoint(rec, scope=data)
        self.invalidate_reports(run_id)

    def load_scope(self, run_id: str) -> dict | None:
        snapshot = load_snapshot(self.root / run_id)
        if snapshot is not None:
            return snapshot.get("scope")
        path = self.root / run_id / "unit_scope.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, rec: RunRecord) -> None:
        rec.dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self._json_path(rec.id), rec.to_dict())

    @staticmethod
    def _write_json(path: Path, payload) -> None:
        atomic_write_json(path, payload)

    @_locked
    def append_terminal_diagnostic(self, run_id, status, error, component="job") -> dict:
        rec = self.get(run_id)
        if rec is None:
            raise ValueError("run not found")
        self.invalidate_reports(run_id)
        saved = RunWriter(rec.dir, run_id).append_terminal_diagnostic(status, error, component)
        self.invalidate_reports(run_id)
        return saved

    @_locked
    def update_target(self, run_id: str, entry: str, base_url: str, source_context: dict | None = None) -> None:
        rec = self.get(run_id)
        if rec is not None:
            self.invalidate_reports(run_id)
            rec.entry = entry
            rec.base_url = base_url
            if source_context is not None:
                rec.source_context = source_context
            self._write(rec)

    @_locked
    def save_diagnostics(self, run_id: str, steps: list, diagnostics: list, incomplete: bool = False) -> None:
        rec = self.get(run_id)
        if rec is not None:
            data = {"steps": steps, "diagnostics": diagnostics, "incomplete": incomplete}
            self.invalidate_reports(run_id)
            self._write_json(rec.dir / "diagnostics.json", data)
            self._update_checkpoint(rec, **data)
            self.invalidate_reports(run_id)

    def load_diagnostics(self, run_id: str) -> dict:
        rec = self.get(run_id)
        if rec is None:
            return {"steps": [], "diagnostics": [], "incomplete": True, "data_status": "absent"}
        try:
            snapshot = load_snapshot(rec.dir)
            if snapshot is not None:
                return {**{key: snapshot[key] for key in ("steps", "diagnostics", "incomplete", "stop_reason")},
                        "checkpoint_seq": snapshot["checkpoint_seq"], "phase": snapshot["phase"],
                        "data_status": "available"}
            path = rec.dir / "diagnostics.json"
            if path.exists():
                data = read_json(path)
                if not isinstance(data, dict) or not isinstance(data.get("steps"), list) or not isinstance(data.get("diagnostics"), list):
                    raise StorageError(f"{path}: invalid diagnostics")
                return {**data, "data_status": "available"}
            return {"steps": [], "diagnostics": [{"stage": "storage", "error": "未保存扫描诊断，检查完整性未知"}],
                    "incomplete": True, "data_status": "absent"}
        except StorageError as exc:
            return {"steps": [], "diagnostics": [{"stage": "storage", "error": str(exc)}],
                    "incomplete": True, "data_status": exc.status}

    @_locked
    def save_replay_result(self, run_id: str, evidence_id: str, result: dict) -> None:
        rec = self.get(run_id)
        if rec is None or Path(evidence_id).name != evidence_id:
            return
        self.invalidate_reports(run_id)
        self._write_json(rec.dir / "replay_results" / f"{evidence_id}.json", result)
        self.invalidate_reports(run_id)

    def load_replay_results(self, run_id: str) -> dict:
        rec = self.get(run_id)
        if rec is None:
            return {}
        directory = rec.dir / "replay_results"
        if not directory.exists():
            return {}
        results = {p.stem: read_json(p) for p in directory.glob("*.json")}
        if any(not isinstance(value, dict) for value in results.values()):
            raise StorageError(f"{directory}: invalid replay result")
        return results

    @_locked
    def invalidate_reports(self, run_id: str) -> None:
        rec = self.get(run_id)
        if rec is not None:
            invalidate_report_paths(rec.dir / name for name in REPORT_FILES.values())

    def _update_checkpoint(self, rec, **updates):
        """Update existing committed authority; legacy runs retain their export path."""
        saved = load_snapshot(rec.dir)
        if saved is not None and any(saved.get(key) != value for key, value in updates.items()):
            self._write_json(rec.dir / "scan.json", {**saved, **updates, "checkpoint_seq": saved["checkpoint_seq"] + 1})

    @_locked
    def load_report_snapshot(self, run_id: str) -> dict:
        rec = self.get(run_id)
        if rec is None:
            raise ValueError("未找到该扫描")
        if rec.status not in TERMINAL_STATUSES:
            raise ValueError("扫描尚未结束，暂时无法生成报告")
        saved = load_snapshot(rec.dir)
        if saved is None:
            def optional(name, default, expected):
                path = rec.dir / name
                data = read_json(path) if path.exists() else default
                if not isinstance(data, expected):
                    raise StorageError(f"{path}: invalid schema")
                return data
            diagnostics = optional("diagnostics.json", {}, dict)
            if (rec.dir / "diagnostics.json").exists() and (
                    not isinstance(diagnostics.get("steps"), list) or not isinstance(diagnostics.get("diagnostics"), list)):
                raise StorageError(f"{rec.dir / 'diagnostics.json'}: invalid diagnostics")
            if not (rec.dir / "evidences.json").exists() and not diagnostics.get("diagnostics"):
                raise StorageError(f"{rec.dir / 'evidences.json'}: required scan results absent", "absent")
            saved = {"evidences": optional("evidences.json", [], list),
                     "investigations": optional("investigations.json", [], list),
                     "scope": optional("unit_scope.json", {}, dict), **diagnostics,
                     "data_status": "legacy；完整性与提交序号未记录"}
            saved.setdefault("steps", [])
            saved.setdefault("diagnostics", [{"stage": "storage", "error": "旧记录缺扫描诊断，完整性未知"}])
            saved.setdefault("incomplete", True)
        elif saved["run_id"] != run_id:
            raise StorageError(f"{rec.dir / 'scan.json'}: run identity mismatch")
        else:
            saved["data_status"] = "available"
        try:
            if any(not isinstance(row, dict) for field in ("evidences", "investigations", "steps", "diagnostics") for row in saved[field]):
                raise ValueError("scan rows must be objects")
            if type(saved.get("incomplete")) is not bool or not isinstance(saved.get("scope"), (dict, type(None))):
                raise ValueError("invalid completeness or scope")
            ids = [row.get("id") for row in saved["evidences"]]
            if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
                raise ValueError("invalid evidence IDs")
            for row in saved["evidences"]:
                for key in ("action", "artifacts", "replay"):
                    if key in row and not isinstance(row[key], dict):
                        raise ValueError(f"invalid evidence {key}")
                for key in ("expectation", "observation_summary", "reasoning", "issue_id", "timestamp"):
                    if key in row and not isinstance(row[key], str):
                        raise ValueError(f"invalid evidence {key}")
            for row in saved["investigations"]:
                if "technical_evidence" in row and not isinstance(row["technical_evidence"], dict):
                    raise ValueError("invalid investigation technical_evidence")
            evidences = [Evidence.from_dict(row) for row in saved["evidences"]]
            investigations = [Investigation.from_dict(row, issue_id=row.get("issue_id", "")) for row in saved["investigations"]]
        except (TypeError, ValueError, AttributeError, KeyError) as exc:
            raise StorageError(f"{rec.dir}: invalid scan results: {exc}") from exc
        diagnostics = list(saved["diagnostics"])
        diagnostics.extend(s for s in saved["steps"] if s.get("status") in
                           {"failed", "inconclusive", "action_failed", "observation_failed"})
        context = {key: saved[key] for key in ("checkpoint_seq", "phase", "stop_reason", "incomplete", "scope", "steps", "data_status") if key in saved}
        context.update(run_id=run_id, status=rec.status, input_type=rec.mode, base_url=rec.base_url,
                       started_at=rec.started_at, finished_at=rec.finished_at, run_dir=str(rec.dir),
                       replay_results=self.load_replay_results(run_id), budget=rec.budget, access_result=saved.get("access_result"), source_context=rec.source_context)
        return {"evidences": evidences, "state": self.load_review(run_id), "investigations": investigations,
                "diagnostics": diagnostics, "scan_context": context}

    @_locked
    def summary(self, run_id: str) -> dict:
        """Counts describe committed work; missing data never implies a clean pass."""
        rec = self.get(run_id)
        if rec is None:
            return {"data_status": "absent"}
        try:
            saved = load_snapshot(rec.dir)
            if saved is None:
                return {"data_status": "absent", "budget": rec.budget}
            if saved["run_id"] != run_id:
                raise StorageError("scan.json belongs to another run")
            rows = saved["evidences"]
            state = self.load_review(run_id)
            steps = saved["steps"]
            statuses = [s.get("cognitive_status", s.get("status")) for s in steps]
            technical = sum(e.get("finding_kind") == "technical_anomaly" for e in rows)
            return {"data_status": "available", "checkpoint_seq": saved["checkpoint_seq"],
                    "phase": saved["phase"], "last_stage": saved.get("last_stage"), "stop_reason": saved["stop_reason"],
                    "incomplete": saved["incomplete"], "attempts": len(steps),
                    "executions": sum(s.get("execution_status") == "completed" or
                                      s.get("execution", {}).get("status") == "ok" for s in steps),
                    "cognitive_completed": sum(s in {"passed", "mismatch"} for s in statuses),
                    "inconclusive": statuses.count("inconclusive"), "failed": statuses.count("failed"),
                    "technical_findings": technical,
                    "cognitive_findings": sum(e.get("finding_kind") == "cognitive_mismatch" for e in rows),
                    "pending": sum(state.decision(e["id"]) == Decision.PENDING for e in rows),
                    "confirmed": sum(state.decision(e["id"]) == Decision.CONFIRMED for e in rows),
                    "evidence_count": len(rows), "issue_count": len(saved.get("issues", [])),
                    "access_result": saved.get("access_result"), "budget": rec.budget,
                    "prompt_versions": sorted({str(s.get("input", {}).get("cognitive", {}).get("prompt_version"))
                                               for s in steps if s.get("input", {}).get("cognitive", {}).get("prompt_version")})}
        except StorageError as exc:
            return {"data_status": exc.status, "error": str(exc), "budget": rec.budget}
        except (TypeError, ValueError, AttributeError) as exc:
            return {"data_status": "corrupt", "error": str(exc), "budget": rec.budget}

    def load_usage(self, run_id: str) -> dict:
        rec = self.get(run_id)
        if rec is None:
            return {"data_status": "absent", "complete": False}
        return load_summary(rec.dir, run_id)

    @_locked
    def finish_usage(self, run_id: str, termination: str) -> None:
        rec = self.get(run_id)
        if rec is None or not (rec.dir / "llm" / "calls").exists():
            return
        try:
            close_unfinished(rec.dir, run_id, termination)
        except (OSError, ValueError) as exc:
            # Existing raw scan remains usable when metering alone is broken.
            from ..llm.metering import public_text
            atomic_write_json(rec.dir / "llm" / "metering-errors.json", [public_text(exc)])
