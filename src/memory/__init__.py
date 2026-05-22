"""Memory and context layer for the Autonomous Red Teaming system.

Separates the model's working set (the context window) from durable memory
(SQLite). Every component is LLM-agnostic with no network calls, so each is
unit-testable in isolation. See README.md in this directory for the design and
safety invariants.
"""
from .context import (
    EPHEMERAL,
    SALIENT,
    MemoryItem,
    PinnedContextMissing,
    WorkingMemory,
    heuristic_token_count,
    make_truncating_summarizer,
)
from .dedup import DedupResult, ExactDeduplicator, content_hash, normalize
from .gc import GCReport, run_gc
from .session import start_engagement
from .store import MemoryStore

__all__ = [
    "WorkingMemory",
    "MemoryItem",
    "PinnedContextMissing",
    "EPHEMERAL",
    "SALIENT",
    "heuristic_token_count",
    "make_truncating_summarizer",
    "MemoryStore",
    "ExactDeduplicator",
    "DedupResult",
    "content_hash",
    "normalize",
    "run_gc",
    "GCReport",
    "start_engagement",
]
