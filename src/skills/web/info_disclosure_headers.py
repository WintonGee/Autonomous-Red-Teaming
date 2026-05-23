"""Skill: detect response headers that leak internal/implementation detail.

The header list is *configuration* (info_disclosure_headers.json), not code:
adding a header to watch for is a config edit. Detection is dynamic — a header is
only reported if the live response actually sends it (and, for version-bearing
headers like Server, only when the value contains a version number). Risk level 1
(passive): a single GET that changes no state.
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

_CONFIG_PATH = Path(__file__).with_name("info_disclosure_headers.json")
_VERSION_RE = re.compile(r"\d+\.\d+|\d")


class InfoDisclosureHeaders(Skill):
    id = "web.info_disclosure_headers"
    name = "Information-Disclosure Headers Check"
    category = "information-disclosure"
    risk_level = 1
    action_type = "web-misconfiguration-checks"
    target_types = ["web-application"]
    tool = "http-client"

    def __init__(self, watch: Optional[list[dict]] = None) -> None:
        self._watch = watch if watch is not None else json.loads(_CONFIG_PATH.read_text())

    def detect(self, response: HttpResponse) -> dict:
        """Pure detection over a single response (unit-testable without I/O)."""
        headers = {k.lower(): v for k, v in response.headers.items()}
        leaked: list[dict] = []
        for entry in self._watch:
            name = entry["header"].lower()
            if name not in headers:
                continue
            value = headers[name]
            if entry.get("version_only") and not _VERSION_RE.search(value or ""):
                continue  # e.g. a Server header with no version is uninteresting
            leaked.append({"header": name, "value": value, "why": entry["why"]})
        return {"status_code": response.status_code, "leaked_headers": leaked}

    def run(self, http: "HttpClient", target_url: str) -> dict:
        obs = self.detect(http.get(target_url))
        if obs["leaked_headers"]:
            names = ", ".join(h["header"] for h in obs["leaked_headers"])
            obs["finding"] = {
                "title": f"Information disclosure via response headers: {names}",
                "category": self.category,
                "severity": "info",
                "confidence": "confirmed",
                "skill_id": self.id,
                "target": target_url,
                "evidence": {
                    "status_code": obs["status_code"],
                    "leaked_headers": obs["leaked_headers"],
                },
            }
        return obs
