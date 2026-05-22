"""Skill base class."""
from __future__ import annotations

from src.tools.http_client import HttpResponse


class Skill:
    """Base for detection skills. Subclasses set metadata and implement detect()."""

    id: str = ""
    name: str = ""
    category: str = ""
    risk_level: int = 0
    action_type: str = ""               # must appear in an authorization's allowed_testing
    target_types: list[str] = []
    tool: str = "http-client"

    def detect(self, response: HttpResponse) -> dict:
        """Pure detection logic over tool output. Returns structured observations."""
        raise NotImplementedError

    def to_record(self) -> dict:
        """Serializable form for the skill registry / semantic memory."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "risk_level": self.risk_level,
            "action_type": self.action_type,
            "target_types": list(self.target_types),
            "tool": self.tool,
        }
