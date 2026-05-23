"""Declarative skill specs — how the system creates *new, runnable* skills safely.

A generated skill is DATA, never code. A `SkillSpec` describes probes (paths to
GET) and a closed set of typed detect conditions; the trusted `SpecSkill`
interpreter executes it through the same gated, rate-limited HttpClient every
other skill uses. The LLM (or a heuristic) only authors the spec — it cannot
execute arbitrary logic, reach beyond GET, or exceed risk level 2.

`coerce_or_reject` is the single trust boundary between an untrusted proposal
(dict) and an executable spec: it validates the schema, caps risk, confirms the
action is authorized, and rejects unsafe probes/patterns. Anything malformed or
over-permissive is dropped, not cleaned.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from src.skills.base import Skill

if TYPE_CHECKING:
    from src.tools.http_client import HttpClient, HttpResponse

# Closed set of detect primitives. The LLM tool-schema and this executor MUST
# agree exactly, so the set lives here and nowhere else.
_CHECKS = {
    "header_present": ("header",),
    "header_absent": ("header",),
    "header_contains": ("header", "substring"),
    "header_lacks": ("header", "substring"),     # header present but value missing substring
    "status_equals": ("value",),
    "body_contains": ("substring",),
    "body_matches": ("pattern",),                # regex, ReDoS-bounded below
}
_MAX_PROBES = 8
_MAX_CONDITIONS = 6
_MAX_PATTERN_LEN = 200
_MAX_SUBSTRING_LEN = 200
_MAX_BODY_SCAN = 200_000          # cap regex input to bound ReDoS blast radius
_SEVERITIES = {"info", "low", "medium", "high"}
_MAX_RISK = 2                      # generated skills are passive/safe-active only


@dataclass
class SkillSpec:
    id: str
    name: str
    category: str
    risk_level: int
    action_type: str
    probes: list[dict]            # [{"path": "/..."}]
    detect: dict                  # {"mode": "any"|"all", "conditions": [ {check, ...} ]}
    severity: str
    title: str
    tags: list[str] = field(default_factory=list)
    source: str = "llm-generated"

    def to_record(self) -> dict:
        return {
            "id": self.id, "name": self.name, "category": self.category,
            "risk_level": self.risk_level, "action_type": self.action_type,
            "probes": self.probes, "detect": self.detect, "severity": self.severity,
            "title": self.title, "tags": sorted(self.tags), "source": self.source,
        }

    @classmethod
    def from_record(cls, rec: dict) -> "SkillSpec":
        return cls(
            id=rec["id"], name=rec["name"], category=rec["category"],
            risk_level=rec["risk_level"], action_type=rec["action_type"],
            probes=rec["probes"], detect=rec["detect"], severity=rec["severity"],
            title=rec["title"], tags=rec.get("tags", []), source=rec.get("source", "llm-generated"),
        )


def _safe_path(path: object) -> bool:
    return (
        isinstance(path, str)
        and path.startswith("/")
        and "://" not in path
        and ".." not in path
        and len(path) <= 256
    )


def _valid_condition(cond: object) -> bool:
    if not isinstance(cond, dict):
        return False
    check = cond.get("check")
    if check not in _CHECKS:
        return False
    for required in _CHECKS[check]:
        if required not in cond:
            return False
    if check == "body_matches":
        pattern = cond["pattern"]
        if not isinstance(pattern, str) or not (0 < len(pattern) <= _MAX_PATTERN_LEN):
            return False
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error:
            return False
    if "substring" in cond and (not isinstance(cond["substring"], str)
                                or len(cond["substring"]) > _MAX_SUBSTRING_LEN):
        return False
    if "header" in cond and not isinstance(cond["header"], str):
        return False
    if check == "status_equals" and not isinstance(cond.get("value"), int):
        return False
    return True


def _signature(category: str, action_type: str, probes: list[dict], detect: dict) -> str:
    """Order-insensitive, normalized identity for a spec's *capability*.

    Two specs that probe the same paths with the same conditions are the same
    skill regardless of ordering, header casing, or title prose."""
    norm_probes = sorted(p.get("path", "") for p in probes)
    norm_conds = sorted(
        json.dumps({k: (v.lower() if isinstance(v, str) and k in ("header", "check") else v)
                    for k, v in c.items()}, sort_keys=True)
        for c in detect.get("conditions", [])
    )
    key = {
        "category": category, "action_type": action_type,
        "mode": detect.get("mode", "any"), "probes": norm_probes, "conditions": norm_conds,
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()


def spec_signature(spec: SkillSpec) -> str:
    return _signature(spec.category, spec.action_type, spec.probes, spec.detect)


def coerce_or_reject(
    proposal: dict, *, allowed_testing: set[str], max_risk: int = _MAX_RISK
) -> Optional[SkillSpec]:
    """The trust boundary: untrusted proposal dict -> validated SkillSpec, or None.

    Rejects (does not repair) anything malformed, over-permissive, or unsafe.
    """
    if not isinstance(proposal, dict):
        return None
    try:
        category = proposal["category"]
        action_type = proposal["action_type"]
        risk_level = proposal["risk_level"]
        probes = proposal["probes"]
        detect = proposal["detect"]
        severity = proposal.get("severity", "info")
    except (KeyError, TypeError):
        return None

    if not isinstance(risk_level, int) or not (0 <= risk_level <= min(max_risk, _MAX_RISK)):
        return None
    if action_type not in allowed_testing:
        return None
    if severity not in _SEVERITIES:
        return None
    if not isinstance(category, str) or not category:
        return None
    if (not isinstance(probes, list) or not probes or len(probes) > _MAX_PROBES
            or not all(isinstance(p, dict) and _safe_path(p.get("path")) for p in probes)):
        return None
    if not isinstance(detect, dict) or detect.get("mode") not in ("any", "all"):
        return None
    conditions = detect.get("conditions")
    if (not isinstance(conditions, list) or not conditions
            or len(conditions) > _MAX_CONDITIONS or not all(_valid_condition(c) for c in conditions)):
        return None

    tags = proposal.get("tags") or []
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        tags = []

    norm_probes = [{"path": p["path"]} for p in probes]
    norm_detect = {"mode": detect["mode"], "conditions": conditions}
    sig = _signature(category, action_type, norm_probes, norm_detect)[:10]
    slug = re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_") or "x"
    spec_id = proposal.get("id") or f"web.generated.{slug}.{sig}"
    name = proposal.get("name") or f"Generated: {category}"
    title = proposal.get("title") or f"{category} issue detected"

    return SkillSpec(
        id=spec_id, name=name, category=category, risk_level=risk_level,
        action_type=action_type, probes=norm_probes, detect=norm_detect,
        severity=severity, title=title, tags=tags, source=proposal.get("source", "llm-generated"),
    )


def _match_condition(cond: dict, resp: "HttpResponse") -> bool:
    headers = {k.lower(): (v or "") for k, v in resp.headers.items()}
    check = cond["check"]
    if check == "header_present":
        return cond["header"].lower() in headers
    if check == "header_absent":
        return cond["header"].lower() not in headers
    if check == "header_contains":
        return cond["substring"].lower() in headers.get(cond["header"].lower(), "").lower()
    if check == "header_lacks":
        h = cond["header"].lower()
        return h in headers and cond["substring"].lower() not in headers[h].lower()
    if check == "status_equals":
        return resp.status_code == cond["value"]
    if check == "body_contains":
        return cond["substring"].lower() in (resp.body or "").lower()
    if check == "body_matches":
        return re.search(cond["pattern"], (resp.body or "")[:_MAX_BODY_SCAN], re.IGNORECASE) is not None
    return False


def evaluate_detect(detect: dict, resp: "HttpResponse") -> bool:
    results = [_match_condition(c, resp) for c in detect["conditions"]]
    return all(results) if detect.get("mode") == "all" else any(results)


class SpecSkill(Skill):
    """Executes a declarative SkillSpec. Generated-skill findings are 'suspected'
    (LLM/heuristic-authored heuristics), never auto-trusted as 'confirmed'."""

    target_types = ["web-application"]
    tool = "http-client"

    def __init__(self, spec: SkillSpec) -> None:
        self.spec = spec
        self.id = spec.id
        self.name = spec.name
        self.category = spec.category
        self.risk_level = spec.risk_level
        self.action_type = spec.action_type

    def run(self, http: "HttpClient", target_url: str) -> dict:
        base = target_url.rstrip("/")
        matched: list[dict] = []
        for probe in self.spec.probes:
            try:
                resp = http.get(base + probe["path"])
            except Exception:
                continue  # unreachable / refused -> nothing to report
            if evaluate_detect(self.spec.detect, resp):
                matched.append({
                    "path": probe["path"], "status": resp.status_code,
                    "snippet": (resp.body or "")[:160].replace("\n", " ").strip(),
                })

        obs = {"checked": len(self.spec.probes), "matched": matched}
        if matched:
            obs["finding"] = {
                "title": self.spec.title,
                "category": self.spec.category,
                "severity": self.spec.severity,
                "confidence": "suspected",
                "skill_id": self.spec.id,
                "source": self.spec.source,
                "target": base,
                "evidence": {"matched": matched},
            }
        return obs

    def to_record(self) -> dict:
        return self.spec.to_record()
