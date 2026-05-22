from datetime import date

import pytest

from src.authorization import (
    AuthorizationError,
    AuthorizationGuard,
    AuthorizationRegistry,
    StaticFingerprinter,
)
from src.risk import RiskEngine

REGISTRY = "authorizations/authorized-targets.json"


def _guard(fingerprint_ok: bool = True, fingerprinter=...) -> AuthorizationGuard:
    fp = StaticFingerprinter(ok=fingerprint_ok) if fingerprinter is ... else fingerprinter
    return AuthorizationGuard(AuthorizationRegistry.load(REGISTRY), RiskEngine(), fingerprinter=fp)


def test_unknown_target_fails_closed():
    with pytest.raises(AuthorizationError):
        _guard().authorize_target("not-in-registry")


def test_expired_authorization_fails_closed():
    with pytest.raises(AuthorizationError):
        _guard().authorize_target("local-juice-shop", today=date(2030, 1, 1))


def test_valid_target_with_matching_identity_authorized():
    auth = _guard(fingerprint_ok=True).authorize_target("local-juice-shop", today=date(2026, 6, 1))
    assert auth.target == "http://localhost:3001"


def test_identity_mismatch_fails_closed():
    # The Nova-class catch, now automated: wrong app at the URL -> refuse.
    with pytest.raises(AuthorizationError):
        _guard(fingerprint_ok=False).authorize_target("local-juice-shop", today=date(2026, 6, 1))


def test_declared_identity_without_fingerprinter_fails_closed():
    with pytest.raises(AuthorizationError):
        _guard(fingerprinter=None).authorize_target("local-juice-shop", today=date(2026, 6, 1))


def test_action_gating():
    guard = _guard()
    auth = guard.authorize_target("local-juice-shop", today=date(2026, 6, 1))
    # allowed action within risk ceiling (medium -> 2) -> no raise
    guard.authorize_action(auth, "web-misconfiguration-checks", 1)
    guard.authorize_action(auth, "reconnaissance", 2)
    # explicitly disallowed action
    with pytest.raises(AuthorizationError):
        guard.authorize_action(auth, "denial-of-service", 1)
    # action not present in allowed_testing
    with pytest.raises(AuthorizationError):
        guard.authorize_action(auth, "totally-unknown-action", 1)
    # over the risk ceiling (3 > medium=2)
    with pytest.raises(AuthorizationError):
        guard.authorize_action(auth, "web-misconfiguration-checks", 3)
