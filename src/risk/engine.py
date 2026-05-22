"""Risk engine: classify actions by risk level and enforce the allowed ceiling.

Risk levels follow the README table:
  0 informational | 1 passive | 2 safe-active | 3 intrusive | 4 prohibited

The project ceiling starts at 1 ("start with levels 0 and 1 only"). The effective
maximum for any engagement is min(authorization risk_limit, project ceiling).
Level 4 (prohibited) is never allowed, regardless of configuration.
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
        """Effective max risk = min(authorization limit, project ceiling)."""
        auth_level = RISK_LIMIT_TO_LEVEL.get(risk_limit, 0)
        return min(auth_level, self.project_ceiling)

    def within(self, risk_level: int, max_allowed: int) -> bool:
        """True only if the action is at/below the ceiling and not prohibited."""
        return 0 <= risk_level <= max_allowed and risk_level < PROHIBITED
