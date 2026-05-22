"""SkillLibrary: the AI-facing catalog the agent references.

Composes execution/governance metadata (from the code SkillRegistry) with
knowledge cards (skills/**/*.json: purpose, when_to_use, detection_approach,
references, tags). The two are disjoint except for `id`, so there is no metadata
to drift. Drafts under skills/_drafts/ and any non-active card are refused.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from src.skills.dedup import duplicate_clusters, find_duplicate
from src.skills.registry import SkillRegistry

# Resolve the library dir relative to the repo, not the caller's cwd.
_LIBRARY_ROOT = Path(__file__).resolve().parents[2] / "skills"


class SkillLibrary:
    def __init__(self, registry: SkillRegistry, knowledge: dict[str, dict]) -> None:
        self._registry = registry
        self._knowledge = knowledge  # id -> knowledge card

    @classmethod
    def load(cls, registry: Optional[SkillRegistry] = None, root: Optional[str] = None) -> "SkillLibrary":
        registry = registry or SkillRegistry.with_defaults()
        root_path = Path(root) if root is not None else _LIBRARY_ROOT
        if not root_path.is_dir():
            raise FileNotFoundError(f"skill library directory not found: {root_path}")
        knowledge: dict[str, dict] = {}
        for path in sorted(root_path.glob("**/*.json")):
            if "_drafts" in path.parts:
                continue  # never load unreviewed drafts
            card = json.loads(path.read_text())
            if card.get("status", "active") != "active":
                continue  # second guard: only active cards
            knowledge[card["id"]] = card
        return cls(registry, knowledge)

    def composed(self, skill_id: str) -> dict:
        """Full card the agent references: code metadata + knowledge (disjoint)."""
        skill = self._registry.get(skill_id)
        mechanical = skill.to_record() if skill else {}
        return {**mechanical, **self._knowledge.get(skill_id, {})}

    def all(self) -> list[dict]:
        ids = {s.id for s in self._registry.all()} | set(self._knowledge)
        return [self.composed(i) for i in sorted(ids)]

    def get(self, skill_id: str) -> Optional[dict]:
        card = self.composed(skill_id)
        return card or None

    def categories(self) -> list[str]:
        return sorted({c["category"] for c in self.all() if c.get("category")})

    def for_category(self, category: str) -> list[dict]:
        return [c for c in self.all() if c.get("category") == category]

    def gaps(self, needed_categories: list[str]) -> list[str]:
        """Needed capabilities that have no skill yet (research-and-create input)."""
        return [c for c in needed_categories if not self.for_category(c)]

    def missing_knowledge(self) -> list[str]:
        """Code skills that lack a knowledge card (a card to write)."""
        return sorted(s.id for s in self._registry.all() if s.id not in self._knowledge)

    def find_duplicate_of(self, card: dict) -> Optional[str]:
        """Existing skill id that duplicates `card`, or None.

        The draft-promotion path must call this before moving a card from
        _drafts/ to active, so a draft that collides with a live skill is caught.
        """
        duplicate = find_duplicate(card, self.all())
        return duplicate.get("id") if duplicate else None


def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect the skill library.")
    parser.add_argument("--dedup", action="store_true", help="report duplicate skills")
    parser.add_argument("--gaps", default="", help="comma-separated capabilities to check for gaps")
    args = parser.parse_args(argv)

    library = SkillLibrary.load()
    if args.dedup:
        clusters = duplicate_clusters(library.all())
        print("duplicate clusters:", clusters or "none")
        return 0
    if args.gaps:
        needed = [c.strip() for c in args.gaps.split(",") if c.strip()]
        print("gaps (no skill yet):", library.gaps(needed) or "none")
        return 0

    print(f"skill library ({len(library.all())} skills):")
    for card in library.all():
        print(f"  - {card.get('id')}  [risk {card.get('risk_level')}] {card.get('category')}")
        print(f"      {card.get('purpose', '(no knowledge card)')}")
        print(f"      refs: {len(card.get('references', []))}  tags: {card.get('tags', [])}")
    missing = library.missing_knowledge()
    if missing:
        print(f"code skills missing a knowledge card: {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
