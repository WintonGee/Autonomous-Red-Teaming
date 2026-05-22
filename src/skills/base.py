"""Skill base class.

A skill carries metadata and detection logic. `run()` may make several *gated*
requests through the injected HttpClient, so detection is always dynamic (driven
by live responses), never hardcoded findings. A skill signals a detected issue by
placing a `finding` dict in the observations it returns; the evaluator confirms
and scores it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools.http_client import HttpClient


class Skill:
    id: str = ""
    name: str = ""
    category: str = ""
    risk_level: int = 0
    action_type: str = ""               # must appear in an authorization's allowed_testing
    target_types: list[str] = []
    tool: str = "http-client"

    def run(self, http: "HttpClient", target_url: str) -> dict:
        """Execute the skill against target_url via gated requests.

        Returns observations. If an issue is detected, include a `finding` dict.
        """
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
