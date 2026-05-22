"""Authorization registry and guard.

Loads authorization entries from JSON and enforces them. The guard is the only
sanctioned path from "I have a target" to "I may act on it".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from src.risk.engine import RiskEngine


class AuthorizationError(Exception):
    """Raised whenever authorization cannot be positively established."""


@dataclass
class Authorization:
    id: str
    target: str
    target_type: str
    allowed_testing: list[str]
    disallowed_testing: list[str]
    risk_limit: str
    valid_from: str
    valid_until: str
    rate_limit: dict = field(default_factory=dict)
    expected_identity: dict = field(default_factory=dict)
    environment: str = ""
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Authorization":
        return cls(
            id=d["id"],
            target=d["target"],
            target_type=d.get("target_type", ""),
            allowed_testing=list(d.get("allowed_testing", [])),
            disallowed_testing=list(d.get("disallowed_testing", [])),
            risk_limit=d.get("risk_limit", "informational"),
            valid_from=d["valid_from"],
            valid_until=d["valid_until"],
            rate_limit=d.get("rate_limit", {}),
            expected_identity=d.get("expected_identity", {}),
            environment=d.get("environment", ""),
            notes=d.get("notes", ""),
        )

    def is_valid_on(self, today: date) -> bool:
        return (
            date.fromisoformat(self.valid_from)
            <= today
            <= date.fromisoformat(self.valid_until)
        )


class AuthorizationRegistry:
    def __init__(self, entries: list[Authorization]) -> None:
        self._by_id = {e.id: e for e in entries}

    @classmethod
    def load(cls, path: str | Path) -> "AuthorizationRegistry":
        data = json.loads(Path(path).read_text())
        return cls([Authorization.from_dict(d) for d in data])

    def get(self, authorization_id: str) -> Optional[Authorization]:
        return self._by_id.get(authorization_id)


class AuthorizationGuard:
    """Gatekeeper. All methods fail closed: any uncertainty raises.

    Identity verification is part of authorization: if an authorization declares
    expected_identity, the live target is fingerprinted and must match before the
    target is authorized. An authorization that declares an identity but has no
    fingerprinter available cannot be verified, so it is refused.
    """

    def __init__(
        self,
        registry: AuthorizationRegistry,
        risk_engine: RiskEngine,
        fingerprinter=None,
    ) -> None:
        self.registry = registry
        self.risk_engine = risk_engine
        self.fingerprinter = fingerprinter

    def authorize_target(self, authorization_id: str, today: Optional[date] = None) -> Authorization:
        today = today or date.today()
        auth = self.registry.get(authorization_id)
        if auth is None:
            raise AuthorizationError(
                f"target {authorization_id!r} is not in the authorization registry"
            )
        if not auth.is_valid_on(today):
            raise AuthorizationError(
                f"authorization {authorization_id!r} is not valid on {today.isoformat()} "
                f"(valid {auth.valid_from}..{auth.valid_until})"
            )
        if auth.expected_identity:
            if self.fingerprinter is None:
                raise AuthorizationError(
                    f"{authorization_id!r} declares expected_identity but no fingerprinter "
                    f"is available to verify it (fail closed)"
                )
            ok, detail = self.fingerprinter.matches(auth.target, auth.expected_identity)
            if not ok:
                raise AuthorizationError(
                    f"target identity mismatch for {authorization_id!r} at {auth.target}: {detail}"
                )
        return auth

    def authorize_action(self, auth: Authorization, action_type: str, risk_level: int) -> None:
        if action_type in auth.disallowed_testing:
            raise AuthorizationError(f"action {action_type!r} is explicitly disallowed")
        if action_type not in auth.allowed_testing:
            raise AuthorizationError(f"action {action_type!r} is not in allowed_testing")
        max_allowed = self.risk_engine.max_allowed(auth.risk_limit)
        if not self.risk_engine.within(risk_level, max_allowed):
            raise AuthorizationError(
                f"risk level {risk_level} exceeds the allowed maximum {max_allowed}"
            )
