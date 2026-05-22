"""Skills: small, inspectable, reusable detection capabilities.

A skill carries metadata (id, risk, action type, tool) and pure detection logic.
It does no I/O itself — the executor supplies tool output — so skills are unit
testable without a network or live target.
"""
from .base import Skill
from .dedup import capability_signature, duplicate_clusters, find_duplicate
from .registry import SkillRegistry
from .web.exposed_sensitive_paths import ExposedSensitivePaths
from .web.missing_security_headers import MissingSecurityHeaders

# Note: SkillLibrary (src.skills.library) and propose_skill_card
# (src.skills.research) are imported from their modules directly, not re-exported
# here, so `python -m src.skills.library` runs without a double-import warning.

__all__ = [
    "Skill",
    "SkillRegistry",
    "MissingSecurityHeaders",
    "ExposedSensitivePaths",
    "capability_signature",
    "find_duplicate",
    "duplicate_clusters",
]
