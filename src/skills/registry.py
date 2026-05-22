"""Skill registry: in-memory lookup plus idempotent seeding into semantic memory."""
from __future__ import annotations

from typing import Optional

from src.memory.store import MemoryStore
from src.skills.base import Skill
from src.skills.web.missing_security_headers import MissingSecurityHeaders


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.id] = skill

    def get(self, skill_id: str) -> Optional[Skill]:
        return self._skills.get(skill_id)

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    @classmethod
    def with_defaults(cls) -> "SkillRegistry":
        registry = cls()
        registry.register(MissingSecurityHeaders())
        return registry

    def seed_semantic(self, store: MemoryStore) -> None:
        """Persist skills as global (reusable) semantic items. Idempotent."""
        existing = {
            row["external_id"]
            for row in store.conn.execute(
                "SELECT external_id FROM semantic_items WHERE kind = 'skill'"
            )
        }
        for skill in self.all():
            if skill.id not in existing:
                store.add_semantic_item(
                    kind="skill",
                    title=skill.name,
                    external_id=skill.id,
                    content=skill.to_record(),
                    tags=[skill.category],
                )
