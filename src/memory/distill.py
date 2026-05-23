"""Learning-loop distillation: episodic experience -> proposed reusable skills.

The deterministic, evidence-grounded half of the learning loop (README Phase 5).
It reads an engagement's persisted `finding` events and proposes a reusable
detection skill for any finding whose *category* has no covering skill yet —
deduped against every skill already known (active or already proposed).

This deliberately complements, not duplicates, the (LLM) Learner:

  - When every finding came from an existing skill — the no-API-key case — every
    category is already covered, so distillation correctly proposes NOTHING.
  - The value appears once the LLM Evaluator surfaces an issue in a category we
    have no skill for (an `extra_finding`, persisted pending_review). Distillation
    turns that one-off discovery into a reusable, human-reviewable skill proposal.
    A reviewer promotes it; the next engagement rediscovers it deterministically
    and the measured rediscovery rate climbs. That loop closure is the point.

Proposals are returned for the caller to persist as status='pending_review';
nothing here auto-creates an executable skill (human review stays in the loop).
"""
from __future__ import annotations

import json

from .store import MemoryStore


def _covered_categories(store: MemoryStore) -> set[str]:
    """Categories already handled by a skill (any status: active or proposed)."""
    covered: set[str] = set()
    for row in store.conn.execute("SELECT tags FROM semantic_items WHERE kind = 'skill'"):
        try:
            covered.update(json.loads(row["tags"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            continue
    return covered


def distill_engagement(store: MemoryStore, engagement_id: str) -> list[dict]:
    """Propose durable skills for finding-categories this engagement left uncovered.

    Returns a list of candidate proposals (dicts) for human review. Empty when
    every finding is already covered by a known skill — which is the correct,
    common result without LLM-surfaced novelty.
    """
    findings: list[dict] = []
    for event in store.get_events(engagement_id):
        if event["event_type"] != "finding":
            continue
        try:
            findings.append(json.loads(event["content"]))
        except (json.JSONDecodeError, TypeError):
            continue
    if not findings:
        return []

    covered = _covered_categories(store)
    proposals: list[dict] = []
    seen: set[str] = set()
    for finding in findings:
        category = finding.get("category", "unknown")
        if category in covered or category in seen:
            continue  # reuse before create: already have (or already proposed) a skill
        seen.add(category)
        proposals.append({
            "title": f"Detect {category}",
            "category": category,
            "rationale": (
                f"Engagement surfaced a '{category}' finding "
                f"({finding.get('title', 'untitled')}) with no covering skill; "
                "propose a reusable detector."
            ),
            "payload": {"seed_finding": finding, "engagement_id": engagement_id},
            "source": "distilled",
        })
    return proposals
