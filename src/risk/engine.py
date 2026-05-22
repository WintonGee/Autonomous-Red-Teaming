"""Risk engine: classify actions by risk level and enforce the allowed ceiling.

Risk levels follow the README table:
  0 informational | 1 passive | 2 safe-active | 3 intrusive | 4 prohibited

A properly-authorized target carries its own risk_limit, and that elevation is
honored directly — the project ceiling is NOT a global cap on properly-authorized
targets (otherwise every new authorization silently inherits one lab's ceiling).
The project ceiling instead acts as the conservative fallback for a missing or
malformed authorization. Level 4 (prohibited) is never allowed, and risk level 3+
should additionally pass the (future) human-approval gate before execution.
"""
from __future__ import annotations

RISK_LIMIT_TO_LEVEL = {
    "informational": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}

RISK_LEVEL_NAMES = {
    0: "informational",
    1: "passive",
    2: "safe-active",
    3: "intrusive",
    4: "prohibited",
}

PROHIBITED = 4


class RiskEngine:
    def __init__(self, project_ceiling: int = 1) -> None:
        self.project_ceiling = project_ceiling

    def max_allowed(self, risk_limit: str) -> int:
        """Max risk for a target.

        A known, properly-authorized risk_limit is honored directly. A missing or
        malformed risk_limit falls back to the conservative project ceiling.
        """
        level = RISK_LIMIT_TO_LEVEL.get(risk_limit)
        if level is None:
            return self.project_ceiling
        return level

    def within(self, risk_level: int, max_allowed: int) -> bool:
        """True only if the action is at/below the ceiling and not prohibited."""
        return 0 <= risk_level <= max_allowed and risk_level < PROHIBITED
