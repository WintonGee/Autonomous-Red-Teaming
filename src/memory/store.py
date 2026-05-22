"""SQLite-backed durable storage for episodic and semantic memory.

The store is deliberately "dumb": it persists/retrieves rows and enforces
authorization scoping on reads. Higher-level policy (compaction, dedup
decisions, GC) lives in the sibling modules.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .dedup import content_hash

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    """Thin, explicit wrapper around a SQLite database."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA_PATH.read_text())
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ----------------------------------------------------------- episodic
    def add_event(
        self,
        *,
        engagement_id: str,
        authorization_id: str,
        event_type: str,
        content: str,
        salience: str = "salient",
        token_cost: int = 0,
        evidence_ref: Optional[int] = None,
        deduplicate: bool = False,
    ) -> int:
        """Append an episodic event; return its id.

        With deduplicate=True, identical (post-normalization) content already
        seen *in this engagement* is not re-inserted: the existing event's id is
        returned and its hit_count is bumped. Dedup is per-engagement (scope is
        keyed by engagement_id) so the same content in a different engagement is
        kept. gc.run_gc remains a sweep-time safety net for non-deduped inserts.
        """
        h = content_hash(content)
        scope = f"episodic:{engagement_id}"
        if deduplicate:
            row = self.conn.execute(
                "SELECT ref_id FROM dedup_hashes WHERE content_hash = ? AND scope = ?",
                (h, scope),
            ).fetchone()
            if row is not None and row["ref_id"] is not None:
                self.conn.execute(
                    "UPDATE dedup_hashes SET hit_count = hit_count + 1 "
                    "WHERE content_hash = ? AND scope = ?",
                    (h, scope),
                )
                self.conn.commit()
                return int(row["ref_id"])
        cur = self.conn.execute(
            """
            INSERT INTO episodic_events
                (engagement_id, authorization_id, ts, event_type,
                 salience, content, content_hash, token_cost, evidence_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (engagement_id, authorization_id, _utcnow(), event_type,
             salience, content, h, token_cost, evidence_ref),
        )
        new_id = int(cur.lastrowid)
        if deduplicate:
            self.conn.execute(
                "INSERT OR IGNORE INTO dedup_hashes "
                "(content_hash, scope, ref_id, first_seen, hit_count) VALUES (?, ?, ?, ?, 1)",
                (h, scope, new_id, _utcnow()),
            )
        self.conn.commit()
        return new_id

    def get_events(self, engagement_id: str) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            "SELECT * FROM episodic_events WHERE engagement_id = ? ORDER BY id",
            (engagement_id,),
        ))

    # ----------------------------------------------------------- semantic
    def add_semantic_item(
        self,
        *,
        kind: str,
        title: str,
        content: Any = "",
        authorization_id: Optional[str] = None,
        external_id: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        source: str = "manual-seed",
        status: str = "active",
    ) -> int:
        # Target-specific knowledge must be scoped to an authorization.
        if kind in ("finding", "target_profile") and not authorization_id:
            raise ValueError(
                f"semantic item kind={kind!r} is target-specific and requires authorization_id"
            )
        payload = content if isinstance(content, str) else json.dumps(content, sort_keys=True)
        now = _utcnow()
        cur = self.conn.execute(
            """
            INSERT INTO semantic_items
                (kind, authorization_id, external_id, title, content,
                 content_hash, tags, source, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (kind, authorization_id, external_id, title, payload,
             content_hash(payload), json.dumps(sorted(tags or [])),
             source, status, now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def retrieve_semantic(
        self,
        *,
        authorization_id: str,
        kinds: Optional[Iterable[str]] = None,
        include_global: bool = True,
        status: str = "active",
    ) -> list[sqlite3.Row]:
        """Return semantic items visible to a given engagement.

        Authorization scoping (fail-closed isolation): an engagement sees items
        tagged with its own authorization_id, plus global (NULL) items such as
        reusable skills when include_global is True. Items belonging to a
        *different* authorization are never returned.
        """
        clauses = ["status = ?"]
        params: list[Any] = [status]
        if include_global:
            clauses.append("(authorization_id = ? OR authorization_id IS NULL)")
        else:
            clauses.append("authorization_id = ?")
        params.append(authorization_id)
        if kinds:
            kinds = list(kinds)
            clauses.append(f"kind IN ({','.join('?' * len(kinds))})")
            params.extend(kinds)
        sql = f"SELECT * FROM semantic_items WHERE {' AND '.join(clauses)} ORDER BY id"
        return list(self.conn.execute(sql, params))

    # ----------------------------------------------------------- evidence
    def add_evidence_ref(
        self,
        *,
        engagement_id: str,
        authorization_id: str,
        path: str,
        sha256: str,
        media_type: Optional[str] = None,
        size_bytes: int = 0,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO evidence_refs
                (engagement_id, authorization_id, path, sha256, media_type, bytes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (engagement_id, authorization_id, path, sha256, media_type, size_bytes, _utcnow()),
        )
        self.conn.commit()
        return int(cur.lastrowid)
