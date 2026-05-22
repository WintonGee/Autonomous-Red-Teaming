"""Authorization: the source of truth for what may be tested.

Every target and action is checked here, in code, before anything touches a
remote system. Checks fail closed: missing, expired, ambiguous, or out-of-scope
authorization stops the run.
"""
from .registry import (
    Authorization,
    AuthorizationError,
    AuthorizationGuard,
    AuthorizationRegistry,
)

__all__ = [
    "Authorization",
    "AuthorizationError",
    "AuthorizationGuard",
    "AuthorizationRegistry",
]
