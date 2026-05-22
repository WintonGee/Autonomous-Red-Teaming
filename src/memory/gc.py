"""Garbage-collection sweep for the durable episodic log.

Distinct from in-context compaction (context.py): the GC sweep operates on the
SQLite episodic log on disk, evicting expired ephemeral events and collapsing
exact duplicates so the log does not grow without bound.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .store import MemoryStore


@dataclass
class GCReport:
    expired_ephemeral: int = 0
    duplicates_collapsed: int = 0


def run_gc(
    store: MemoryStore,
    *,
    ephemeral_ttl: timedelta = timedelta(hours=24),
    now: datetime | None = None,
) -> GCReport:
    """Run one GC pass over the episodic log and return a report of what changed."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - ephemeral_ttl).isoformat()
    report = GCReport()

    # 1. Evict expired ephemeral events. Salient/pinned events are retained.
    cur = store.conn.execute(
        "DELETE FROM episodic_events WHERE salience = 'ephemeral' AND ts < ?",
        (cutoff,),
    )
    report.expired_ephemeral = cur.rowcount

    # 2. Collapse exact duplicates within each engagement, keeping the earliest
    #    occurrence of every (engagement_id, content_hash).
    cur = store.conn.execute(
        """
        DELETE FROM episodic_events
        WHERE id NOT IN (
            SELECT MIN(id) FROM episodic_events
            GROUP BY engagement_id, content_hash
        )
        """
    )
    report.duplicates_collapsed = cur.rowcount
    store.conn.commit()
    return report
