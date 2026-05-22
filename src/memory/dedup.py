"""Exact (hash-based) deduplication.

Phase 1 is exact dedup: normalize text, hash it, treat identical hashes as
duplicates. This is fast, dependency-free, and catches identical re-fetches and
repeated tool output.

Phase 2 (semantic / embedding near-dup) will layer on top using the reserved
`embedding` column in semantic_items. It is intentionally not built yet.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .store import MemoryStore

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Canonicalize text for comparison: trim, lowercase, collapse whitespace."""
    return _WS.sub(" ", text.strip().lower())


def content_hash(text: str) -> str:
    """Stable SHA-256 of the normalized text."""
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


@dataclass
class DedupResult:
    is_duplicate: bool
    content_hash: str
    hit_count: int


class ExactDeduplicator:
    """Maintains the dedup_hashes registry for O(1) exact-duplicate detection."""

    def __init__(self, store: "MemoryStore") -> None:
        self.store = store

    def check_and_register(
        self, content: str, *, scope: str, ref_id: Optional[int] = None
    ) -> DedupResult:
        """Return whether `content` has been seen before in `scope`, and record it.

        First sight returns is_duplicate=False and registers the hash. Every
        later identical (post-normalization) content returns is_duplicate=True
        and increments hit_count.
        """
        h = content_hash(content)
        row = self.store.conn.execute(
            "SELECT hit_count FROM dedup_hashes WHERE content_hash = ? AND scope = ?",
            (h, scope),
        ).fetchone()
        if row is None:
            self.store.conn.execute(
                "INSERT INTO dedup_hashes (content_hash, scope, ref_id, first_seen, hit_count) "
                "VALUES (?, ?, ?, ?, 1)",
                (h, scope, ref_id, datetime.now(timezone.utc).isoformat()),
            )
            self.store.conn.commit()
            return DedupResult(False, h, 1)
        new_count = int(row["hit_count"]) + 1
        self.store.conn.execute(
            "UPDATE dedup_hashes SET hit_count = ? WHERE content_hash = ? AND scope = ?",
            (new_count, h, scope),
        )
        self.store.conn.commit()
        return DedupResult(True, h, new_count)
