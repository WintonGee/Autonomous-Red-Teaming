"""Scorer: records the outcome of every skill run and reports rolling stats.

This persists in the same SQLite database as memory, so metrics survive across
cycles. The planner reads these stats to prioritize skills — that feedback,
accumulated run over run, is what "continuously improve" means here.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

_DDL = """
CREATE TABLE IF NOT EXISTS skill_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id          TEXT NOT NULL,
    authorization_id  TEXT NOT NULL,
    ts                TEXT NOT NULL,
    had_signal        INTEGER NOT NULL,
    finding_confirmed INTEGER NOT NULL,
    error             TEXT
);
CREATE INDEX IF NOT EXISTS idx_skill_runs_skill ON skill_runs(skill_id);
"""


@dataclass
class SkillStats:
    skill_id: str
    runs: int = 0
    signals: int = 0
    confirmed: int = 0

    @property
    def signal_ratio(self) -> float:
        return self.signals / self.runs if self.runs else 0.0


class Scorer:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.executescript(_DDL)
        self.conn.commit()

    def record(
        self,
        *,
        skill_id: str,
        authorization_id: str,
        had_signal: bool,
        finding_confirmed: bool,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO skill_runs "
            "(skill_id, authorization_id, ts, had_signal, finding_confirmed, error) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                skill_id,
                authorization_id,
                datetime.now(timezone.utc).isoformat(),
                int(had_signal),
                int(finding_confirmed),
                error,
            ),
        )
        self.conn.commit()

    def stats(self, skill_id: str) -> SkillStats:
        row = self.conn.execute(
            "SELECT COUNT(*) AS runs, "
            "       COALESCE(SUM(had_signal), 0) AS signals, "
            "       COALESCE(SUM(finding_confirmed), 0) AS confirmed "
            "FROM skill_runs WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
        return SkillStats(
            skill_id=skill_id,
            runs=int(row["runs"]),
            signals=int(row["signals"]),
            confirmed=int(row["confirmed"]),
        )
