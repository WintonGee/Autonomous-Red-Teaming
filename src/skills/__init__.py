"""Skills: small, inspectable, reusable detection capabilities.

A skill carries metadata (id, risk, action type, tool) and pure detection logic.
It does no I/O itself — the executor supplies tool output — so skills are unit
testable without a network or live target.
"""
from .base import Skill
from .registry import SkillRegistry
from .web.missing_security_headers import MissingSecurityHeaders

__all__ = ["Skill", "SkillRegistry", "MissingSecurityHeaders"]
