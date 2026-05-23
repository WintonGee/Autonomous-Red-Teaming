"""Skill: detect permissive CORS configuration (risk level 1, passive).

A wildcard `Access-Control-Allow-Origin: *` is a misconfiguration but not, on its
own, proof of an exploitable flaw — a genuinely public API may set it on purpose.
So a bare wildcard is reported as *suspected* (verify the endpoint is not
credentialed). It is escalated to *confirmed* (and higher severity) only when the
response also sends `Access-Control-Allow-Credentials: true`, which lets any
origin read authenticated responses — a real account-takeover-class flaw.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.skills.base import Skill
from src.tools.http_client import HttpResponse

if TYPE_CHECKING:
    from src.tools.http_client import HttpClient


class CorsMisconfiguration(Skill):
    id = "web.cors_misconfiguration"
    name = "Permissive CORS Check"
    category = "cors-misconfiguration"
    risk_level = 1
    action_type = "web-misconfiguration-checks"
    target_types = ["web-application"]
    tool = "http-client"

    def detect(self, response: HttpResponse) -> dict:
        """Pure detection over a single response (unit-testable without I/O)."""
        headers = {k.lower(): v for k, v in response.headers.items()}
        acao = headers.get("access-control-allow-origin")
        acac = (headers.get("access-control-allow-credentials") or "").lower() == "true"
        wildcard = acao == "*"
        return {
            "status_code": response.status_code,
            "access_control_allow_origin": acao,
            "access_control_allow_credentials": acac,
            "wildcard": wildcard,
            "with_credentials": wildcard and acac,
        }

    def run(self, http: "HttpClient", target_url: str) -> dict:
        obs = self.detect(http.get(target_url))
        if obs["wildcard"]:
            credentialed = obs["with_credentials"]
            obs["finding"] = {
                "title": (
                    "Wildcard CORS with credentials (any origin can read authenticated responses)"
                    if credentialed
                    else "Permissive CORS: Access-Control-Allow-Origin: *"
                ),
                "category": self.category,
                "severity": "high" if credentialed else "low",
                "confidence": "confirmed" if credentialed else "suspected",
                "skill_id": self.id,
                "target": target_url,
                "evidence": {
                    "status_code": obs["status_code"],
                    "access_control_allow_origin": obs["access_control_allow_origin"],
                    "access_control_allow_credentials": obs["access_control_allow_credentials"],
                },
            }
        return obs
