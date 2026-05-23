"""Skill: detect verbose error responses that leak internal detail (risk 2).

Probe paths are *configuration* (verbose_error_probes.json), not code. Each probe
is a read-only GET expected to trigger an error; the response is inspected for
error-page signatures (stack frames, framework error classes). This is risk
level 2 (safe-active): it sends controlled requests that may exercise error
handling but changes no state and does not attempt exploitation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from src.skills.base import Skill
from src.tools.http_client import HttpResponse

if TYPE_CHECKING:
    from src.tools.http_client import HttpClient

_PROBES_PATH = Path(__file__).with_name("verbose_error_probes.json")

# Signatures that should never appear in a well-behaved production response.
_SIGNATURES: list[tuple[str, re.Pattern]] = [
    ("stack_frame", re.compile(r"\bat\s+[\w./\\-]+:\d+", re.IGNORECASE)),
    ("error_class", re.compile(r"\b(?:Sequelize\w*Error|ValidationError|UnauthorizedError|TypeError|ReferenceError)\b")),
    ("exception_label", re.compile(r"(?:Traceback \(most recent call last\)|Exception in thread)")),
]


class VerboseErrors(Skill):
    id = "web.verbose_errors"
    name = "Verbose Error Disclosure Check"
    category = "error-handling"
    risk_level = 2
    action_type = "safe-validation"
    target_types = ["web-application"]
    tool = "http-client"

    def __init__(self, probes: Optional[list[dict]] = None) -> None:
        self._probes = probes if probes is not None else json.loads(_PROBES_PATH.read_text())

    def detect(self, response: HttpResponse) -> list[str]:
        """Signature names found in a response body (pure; unit-testable)."""
        return [name for name, pattern in _SIGNATURES if pattern.search(response.body or "")]

    def run(self, http: "HttpClient", target_url: str) -> dict:
        base = target_url.rstrip("/")
        leaks: list[dict] = []
        for probe in self._probes:
            try:
                resp = http.get(base + probe["path"])
            except Exception:
                continue  # unreachable / refused -> nothing to report
            signatures = self.detect(resp)
            if signatures:
                leaks.append({
                    "path": probe["path"],
                    "status": resp.status_code,
                    "signatures": signatures,
                    "why": probe["why"],
                    "snippet": (resp.body or "")[:200].replace("\n", " ").strip(),
                })

        obs = {"checked": len(self._probes), "verbose_errors": leaks}
        if leaks:
            obs["finding"] = {
                "title": f"Verbose error disclosure on {len(leaks)} endpoint(s)",
                "category": self.category,
                "severity": "low",
                "confidence": "confirmed",
                "skill_id": self.id,
                "target": base,
                "evidence": {"verbose_errors": leaks},
            }
        return obs
