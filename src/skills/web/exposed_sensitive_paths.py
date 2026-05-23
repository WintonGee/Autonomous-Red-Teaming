"""Skill: detect sensitive resources reachable without authentication.

The probe list is *configuration* (exposed_sensitive_paths.json), not code:
adding a path is a config edit, the detection logic is unchanged. Detection is
dynamic — a path is only reported if the live response actually returns it (and,
where given, contains the expected confidential marker). This is risk level 2
(safe-active): it sends several controlled GET requests but changes no state.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from src.skills.base import Skill

if TYPE_CHECKING:
    from src.tools.http_client import HttpClient

_PROBES_PATH = Path(__file__).with_name("exposed_sensitive_paths.json")


class ExposedSensitivePaths(Skill):
    id = "web.exposed_sensitive_paths"
    name = "Exposed Sensitive Paths Check"
    category = "broken-access-control"
    risk_level = 2
    action_type = "reconnaissance"
    target_types = ["web-application"]
    tool = "http-client"

    def __init__(self, probes: Optional[list[dict]] = None) -> None:
        self._probes = probes if probes is not None else json.loads(_PROBES_PATH.read_text())

    def run(self, http: "HttpClient", target_url: str) -> dict:
        base = target_url.rstrip("/")
        exposed: list[dict] = []
        for probe in self._probes:
            try:
                resp = http.get(base + probe["path"])
            except Exception:
                continue  # unreachable / refused -> not exposed
            if resp.status_code != 200:
                continue
            marker = probe.get("expect_contains")
            # Evidence over claims: a bare 200 is NOT proof a resource is sensitive.
            # Single-page apps return 200 + index.html for unknown paths, so require
            # a content marker the app shell would not contain before reporting.
            if not marker or marker.lower() not in resp.body.lower():
                continue
            exposed.append({
                "path": probe["path"],
                "status": resp.status_code,
                "why": probe["why"],
                "snippet": resp.body[:160].replace("\n", " ").strip(),
            })

        obs = {"checked": len(self._probes), "exposed": exposed}
        if exposed:
            obs["finding"] = {
                "title": f"{len(exposed)} sensitive resource(s) reachable without authentication",
                "category": self.category,
                "severity": "medium",
                "confidence": "confirmed",
                "skill_id": self.id,
                "target": base,
                "evidence": {"exposed": exposed},
            }
        return obs

    def to_record(self) -> dict:
        record = super().to_record()
        record["probe_count"] = len(self._probes)
        return record
