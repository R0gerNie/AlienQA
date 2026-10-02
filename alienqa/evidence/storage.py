"""Evidence 存储：SQLite（stdlib sqlite3，零新依赖）。"""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .models import Evidence


class EvidenceStore:
    def __init__(self, db_path="evidence.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("BEGIN")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    action TEXT,
                    expectation TEXT,
                    observation_summary TEXT,
                    reasoning TEXT,
                    severity TEXT,
                    classification TEXT,
                    confidence REAL,
                    timestamp TEXT,
                    artifacts TEXT,
                    replay TEXT
                )"""
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(evidence)")}
            for name in ("issue_id", "before_state_id", "after_state_id"):
                if name not in columns:
                    conn.execute(f"ALTER TABLE evidence ADD COLUMN {name} TEXT DEFAULT ''")
            additions = {"schema_version": "INTEGER", "finding_kind": "TEXT", "expectation_basis": "TEXT",
                         "run_id": "TEXT DEFAULT ''", "step_id": "TEXT", "action_id": "TEXT",
                         "source_record_ids": "TEXT DEFAULT '[]'", "expectation_id": "TEXT"}
            for name, declaration in additions.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE evidence ADD COLUMN {name} {declaration}")


    def insert(self, evidence: Evidence) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                """INSERT OR REPLACE INTO evidence
                   (id, action, expectation, observation_summary, reasoning, severity,
                    classification, confidence, timestamp, artifacts, replay,
                    issue_id, before_state_id, after_state_id, schema_version, finding_kind,
                    expectation_basis, run_id, step_id, action_id, source_record_ids, expectation_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    evidence.id,
                    json.dumps(evidence.action, ensure_ascii=False),
                    evidence.expectation,
                    evidence.observation_summary,
                    evidence.reasoning,
                    evidence.severity.value,
                    evidence.classification,
                    evidence.confidence,
                    evidence.timestamp,
                    json.dumps(evidence.artifacts, ensure_ascii=False),
                    json.dumps(evidence.replay, ensure_ascii=False),
                    evidence.issue_id,
                    evidence.before_state_id,
                    evidence.after_state_id,
                    evidence.schema_version,
                    evidence.finding_kind,
                    json.dumps(evidence.expectation_basis, ensure_ascii=False),
                    evidence.run_id,
                    evidence.step_id,
                    evidence.action_id,
                    json.dumps(evidence.source_record_ids),
                    evidence.expectation_id,
                ),
            )

    def all_ids(self) -> list:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute("SELECT id FROM evidence ORDER BY id").fetchall()
        return [r[0] for r in rows]

    def get(self, evidence_id: str) -> Evidence | None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        for key, default in (("action", {}), ("artifacts", {}), ("replay", {}),
                             ("expectation_basis", None), ("source_record_ids", [])):
            data[key] = json.loads(data[key]) if data.get(key) else default
        return Evidence.from_dict(data)
