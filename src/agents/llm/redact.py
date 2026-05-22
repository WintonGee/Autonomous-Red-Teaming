"""Redaction for anything sent to an external AI model.

Charter: "redact obvious secrets from AI prompts" and "avoid sending
credentials, private keys, session tokens ... to external AI services". This
strips credential-shaped secrets and truncates oversized content before any
evidence leaves the process.

Policy note: for the local, owned learning-lab targets this project tests, we DO
send truncated response-body snippets (they are our own intentionally-vulnerable
test data) after stripping credential patterns. For real third-party targets a
stricter policy should apply — do not send response bodies at all without
explicit human approval. That stricter mode is a deliberate TODO, not built here.
"""
from __future__ import annotations

import re

_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}")
_PROVIDER_KEY = re.compile(r"\b(?:sk|pk|rk|ghp|gho|xox[baprs])[-_][A-Za-z0-9_-]{12,}\b")
_AWS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_LONG_HEX = re.compile(r"\b[A-Fa-f0-9]{32,}\b")
# key: value / key = value where the key name implies a secret
_KV_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|secret(?:[_-]?key)?|access[_-]?token|auth[_-]?token|token|password|passwd|pwd)\b"
    r"(\s*[:=]\s*|\s+)"
    r"([^\s\"',;}]{3,})"
)

# (pattern, replacement) — replacement is a string or a callable for re.sub.
_RULES: list[tuple[re.Pattern, object]] = [
    (_PRIVATE_KEY, "[REDACTED:PRIVATE_KEY]"),
    (_JWT, "[REDACTED:JWT]"),
    (_BEARER, "Bearer [REDACTED]"),
    (_PROVIDER_KEY, "[REDACTED:API_KEY]"),
    (_AWS_KEY, "[REDACTED:AWS_KEY]"),
    (_KV_SECRET, lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]"),
    (_LONG_HEX, "[REDACTED:HEX]"),
]

MAX_LEN = 4000


def redact(text: str, max_len: int = MAX_LEN) -> tuple[str, int]:
    """Return (redacted_text, redaction_count). Truncates to max_len."""
    if not isinstance(text, str):
        text = str(text)
    count = 0
    for pattern, repl in _RULES:
        text, n = pattern.subn(repl, text)
        count += n
    if len(text) > max_len:
        text = text[:max_len] + " …[truncated]"
    return text, count
