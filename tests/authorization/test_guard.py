from datetime import date

import pytest

from src.authorization import AuthorizationError, AuthorizationGuard, AuthorizationRegistry
from src.risk import RiskEngine

REGISTRY = "authorizations/authorized-targets.json"


def _guard(ceiling: int = 1) -> AuthorizationGuard:
    return AuthorizationGuard(AuthorizationRegistry.load(REGISTRY), RiskEngine(project_ceiling=ceiling))


def test_unknown_target_fails_closed():
    with pytest.raises(AuthorizationError):
        _guard().authorize_target("not-in-registry")


def test_expired_authorization_fails_closed():
    with pytest.raises(AuthorizationError):
        _guard().authorize_target("local-juice-shop", today=date(2030, 1, 1))


def test_valid_target_authorized():
    auth = _guard().authorize_target("local-juice-shop", today=date(2026, 6, 1))
    assert auth.target == "http://localhost:3000"


def test_action_gating():
    guard = _guard()
    auth = guard.authorize_target("local-juice-shop", today=date(2026, 6, 1))
    # allowed action within risk ceiling -> no raise
    guard.authorize_action(auth, "web-misconfiguration-checks", 1)
    # explicitly disallowed action
    with pytest.raises(AuthorizationError):
        guard.authorize_action(auth, "denial-of-service", 1)
    # action not present in allowed_testing
    with pytest.raises(AuthorizationError):
        guard.authorize_action(auth, "totally-unknown-action", 1)
    # over the risk ceiling
    with pytest.raises(AuthorizationError):
        guard.authorize_action(auth, "web-misconfiguration-checks", 3)
