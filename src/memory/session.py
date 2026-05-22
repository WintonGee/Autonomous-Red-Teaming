"""Engagement session helpers — the session boundary for working memory.

Each engagement starts a *fresh* WorkingMemory seeded with pinned safety facts
and relevant durable knowledge retrieved (and authorization-scoped) from
semantic memory. This is the other half of "self-clearing": junk never leaks
across engagements because every engagement gets a clean working set.
"""
from __future__ import annotations

from typing import Mapping

from .context import SALIENT, WorkingMemory
from .store import MemoryStore


def start_engagement(
    store: MemoryStore,
    *,
    authorization_id: str,
    authorization_facts: Mapping[str, object],
    goal: str,
    token_budget: int = 8000,
    recent_keep: int = 6,
    load_skills: bool = True,
) -> WorkingMemory:
    """Create a clean working memory for a new engagement.

    Pinned facts (authorization, scope, goal) are added first and can never be
    evicted. Reusable skills relevant to this authorization are then seeded.
    """
    wm = WorkingMemory(token_budget=token_budget, recent_keep=recent_keep)

    # Pin safety-critical facts first — these can never be evicted.
    wm.pin(f"authorization_id: {authorization_id}")
    for key, value in authorization_facts.items():
        wm.pin(f"{key}: {value}")
    wm.pin(f"goal: {goal}")

    # Seed reusable skills, scoped to this authorization (+ global skills).
    if load_skills:
        for row in store.retrieve_semantic(authorization_id=authorization_id, kinds=("skill",)):
            wm.add(f"skill[{row['external_id']}]: {row['title']}", salience=SALIENT)

    return wm
