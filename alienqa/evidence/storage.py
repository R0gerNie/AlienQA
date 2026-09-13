"""Evidence 存储：SQLite（stdlib sqlite3，零新依赖）。"""
import json
import sqlite3
from pathlib import Path

from .models import Evidence


class EvidenceStore:
    def __init__(self, db_path="evidence.db"):
        self.db_path = Path(db_path)
        self._init_schema()

    def _init_schema(self):
        conn = sqlite3.connect(self.db_path)
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
        conn.commit()
        conn.close()

    def insert(self, evidence: Evidence) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?)",
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
            ),
        )
        conn.commit()
        conn.close()

    def all_ids(self) -> list:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT id FROM evidence ORDER BY id").fetchall()
        conn.close()
        return [r[0] for r in rows]
