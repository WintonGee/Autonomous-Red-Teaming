"""Skill-library deduplication — keep the library from bloating.

"Reuse before create" applied to skills: a new card duplicates an existing one
if it shares an id, or a capability signature (category + action_type + sorted
tags). This is deterministic exact matching, not a fuzzy threshold. Semantic
near-duplicate detection (embeddings) is Phase 2, matching the memory layer.
"""
from __future__ import annotations

import json
from typing import Optional

from src.memory.dedup import content_hash


def capability_signature(card: dict) -> str:
    """A deterministic identity for a skill's capability (not its prose)."""
    key = {
        "category": card.get("category"),
        "action_type": card.get("action_type"),
        "tags": sorted(card.get("tags", [])),
    }
    return content_hash(json.dumps(key, sort_keys=True))


def find_duplicate(card: dict, existing: list[dict]) -> Optional[dict]:
    """Return the first existing card that duplicates `card`, or None."""
    signature = capability_signature(card)
    for other in existing:
        if other.get("id") == card.get("id"):
            return other
        if capability_signature(other) == signature:
            return other
    return None


def duplicate_clusters(cards: list[dict]) -> list[list[str]]:
    """Group skill ids that share a capability signature (for a dedup report)."""
    by_signature: dict[str, list[str]] = {}
    for card in cards:
        by_signature.setdefault(capability_signature(card), []).append(card.get("id"))
    return [ids for ids in by_signature.values() if len(ids) > 1]


def dedupe_specs(candidates, *, existing_specs=(), existing_skill_cards=()):
    """Filter generated SkillSpec candidates down to the genuinely-new ones.

    Three of the five dedupe layers live here (prompt-level and persistence are
    elsewhere):
      - structural: drop a candidate whose order-insensitive spec signature already
        exists (among trusted/generated specs or an earlier candidate this batch);
      - id: drop a candidate whose deterministic id already exists;
      - reuse-before-create: drop a candidate whose capability signature
        (category + action_type + tags) is already covered by a trusted skill.
    """
    from src.skills.spec import spec_signature  # local import avoids any import order risk

    seen_sig = {spec_signature(s) for s in existing_specs}
    seen_id = {s.id for s in existing_specs}
    covered_cap = {capability_signature(c) for c in existing_skill_cards}
    unique = []
    for cand in candidates:
        sig = spec_signature(cand)
        if sig in seen_sig or cand.id in seen_id or capability_signature(cand.to_record()) in covered_cap:
            continue
        seen_sig.add(sig)
        seen_id.add(cand.id)
        unique.append(cand)
    return unique
