"""Skill: detect missing HTTP security headers (risk level 1, passive)."""
from __future__ import annotations

from src.skills.base import Skill
from src.tools.http_client import HttpResponse

REQUIRED_HEADERS = [
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "strict-transport-security",
    "referrer-policy",
]


class MissingSecurityHeaders(Skill):
    id = "web.missing_security_headers"
    name = "Missing Security Headers Check"
    category = "web-misconfiguration"
    risk_level = 1
    action_type = "web-misconfiguration-checks"
    target_types = ["web-application"]
    tool = "http-client"

    def detect(self, response: HttpResponse) -> dict:
        observed = {k.lower() for k in response.headers}
        missing = [h for h in REQUIRED_HEADERS if h not in observed]
        return {
            "status_code": response.status_code,
            "observed_headers": sorted(observed),
            "missing_headers": missing,
            "recommendations": [f"Add the {h} header" for h in missing],
        }
