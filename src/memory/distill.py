"""Learning-loop seam (NOT YET IMPLEMENTED).

This is where episodic experience becomes durable skill — the "self-learning"
half of the system (README Phase 5). The intended pipeline:

    episodic log  ->  end-of-engagement distillation
                  ->  propose candidate skills / patterns
                  ->  dedup against existing semantic memory
                  ->  human review (required for generated skills)
                  ->  write to semantic memory (status='pending_review')

It is deliberately left as a stub so the memory layer can be built and tested
first. Wiring it up requires the AI planning layer (README Phase 4).
"""
from __future__ import annotations

from .store import MemoryStore


def distill_engagement(store: MemoryStore, engagement_id: str) -> list[dict]:
    """Propose durable skills/patterns from an engagement's episodic log.

    Returns a list of candidate proposals for human review. Not implemented yet.
    """
    raise NotImplementedError(
        "Learning-loop distillation is a planned seam (README Phase 5). "
        "Build the AI planning layer before wiring this up."
    )
