"""历史扫描目录管理：每次扫描 = 一个目录，元数据写入 run.json。"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from ..evidence import Evidence, Severity
from ..investigation import Investigation
from ..review import Decision, ReviewState


def _slug(name: str) -> str:
    name = (name or "project").strip()
    name = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "-", name).strip("-")
    return name or "project"


def _evidence_to_dict(e: Evidence) -> dict:
    severity = e.severity
    return {
        "id": e.id,
        "issue_id": e.issue_id,
        "expectation": e.expectation,
        "observation_summary": e.observation_summary,
        "reasoning": e.reasoning,
        "severity": severity.value if isinstance(severity, Severity) else str(severity),
        "classification": e.classification,
        "confidence": e.confidence,
        "action": e.action,
        "replay": e.replay,
        "artifacts": e.artifacts,
        "timestamp": e.timestamp,
    }


def _evidence_from_dict(d: dict) -> Evidence:
    return Evidence(
        id=d.get("id", ""),
        issue_id=d.get("issue_id", ""),
        expectation=d.get("expectation", ""),
        observation_summary=d.get("observation_summary", ""),
        reasoning=d.get("reasoning", ""),
        severity=Severity(d.get("severity", "minor")),
        classification=d.get("classification", "other"),
        confidence=float(d.get("confidence", 0.5)),
        action=d.get("action") or {},
        replay=d.get("replay") or {},
        artifacts=d.get("artifacts") or {},
        timestamp=d.get("timestamp", ""),
    )


@dataclass
class RunRecord:
    """一次扫描的元数据。"""

    id: str
    dir: Path | None = None  # 由 RunManager.get() 回填
    project_path: str = ""
    unit: str = ""
    entry: str = "index.html"
    started_at: str = ""
    finished_at: str = ""
    status: str = "running"  # running | done | error | unknown
    evidence_count: int = 0
    issue_count: int = 0
    accepted_count: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_path": self.project_path,
            "unit": self.unit,
            "entry": self.entry,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "evidence_count": self.evidence_count,
            "issue_count": self.issue_count,
            "accepted_count": self.accepted_count,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RunRecord":
        return cls(
            id=str(d.get("id") or ""),
            project_path=str(d.get("project_path") or ""),
            unit=str(d.get("unit") or ""),
            entry=str(d.get("entry") or "index.html"),
            started_at=str(d.get("started_at") or ""),
            finished_at=str(d.get("finished_at") or ""),
            status=str(d.get("status") or "unknown"),
            evidence_count=int(d.get("evidence_count") or 0),
            issue_count=int(d.get("issue_count") or 0),
            accepted_count=int(d.get("accepted_count") or 0),
            error=str(d.get("error") or ""),
        )


class RunManager:
    """runs_dir 下每个子目录是一次扫描；run.json 记录元数据。"""

    def __init__(self, runs_dir: str | Path):
        self.root = Path(runs_dir)

    def create(self, project_path: str, unit: str = "", entry: str = "index.html") -> RunRecord:
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
            entry=entry,
            started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            status="running",
        )
        self._write(rec)
        return rec

    def finish(self, run_id: str, status: str, evidence_count: int = 0,
               issue_count: int = 0, accepted_count: int = 0, error: str = "") -> None:
        rec = self.get(run_id)
        if rec is None:
            return
        rec.status = status
        rec.evidence_count = evidence_count
        rec.issue_count = issue_count
        rec.accepted_count = accepted_count
        rec.error = error
        rec.finished_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._write(rec)

    def get(self, run_id: str) -> RunRecord | None:
        path = self._json_path(run_id)
        if not path.exists():
            return None
        rec = RunRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
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
        return out

    def _json_path(self, run_id: str) -> Path:
        return self.root / run_id / "run.json"

    # ---- 扫描结果与审核状态持久化 ----

    def save_results(self, run_id: str, evidences: list, investigations: list) -> None:
        rec = self.get(run_id)
        if rec is None:
            return
        (rec.dir / "evidences.json").write_text(
            json.dumps([_evidence_to_dict(e) for e in evidences], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (rec.dir / "investigations.json").write_text(
            json.dumps([i.to_dict() for i in investigations], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_evidences(self, run_id: str) -> list:
        path = self.root / run_id / "evidences.json"
        if not path.exists():
            return []
        return [_evidence_from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]

    def load_investigations(self, run_id: str) -> list:
        path = self.root / run_id / "investigations.json"
        if not path.exists():
            return []
        return [Investigation.from_dict(d, issue_id=d.get("issue_id", ""))
                for d in json.loads(path.read_text(encoding="utf-8"))]

    def save_review(self, run_id: str, state: ReviewState) -> None:
        rec = self.get(run_id)
        if rec is None:
            return
        (rec.dir / "review.json").write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_review(self, run_id: str) -> ReviewState:
        state = ReviewState()
        path = self.root / run_id / "review.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for ev_id, v in data.items():
                state.decide(ev_id, Decision(v["decision"]), v.get("note", ""))
        return state

    def _write(self, rec: RunRecord) -> None:
        rec.dir.mkdir(parents=True, exist_ok=True)
        self._json_path(rec.id).write_text(
            json.dumps(rec.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
