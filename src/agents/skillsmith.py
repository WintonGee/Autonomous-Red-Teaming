"""Skillsmith: turn a site understanding into new, runnable, deduped skills.

This is the create-new-skills half of the autonomous loop. A swappable reasoner
proposes raw spec dicts; `generate_skills` runs them through the trust boundary
(`coerce_or_reject`) and the dedupe layers, returning only safe, genuinely-new
SkillSpecs. Generated specs persist under skills/_generated/ (gitignored, NOT in
the trusted default registry) so the library grows across runs without polluting
the curated set; promotion to the trusted library stays a human decision.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from src.skills.dedup import dedupe_specs
from src.skills.spec import SkillSpec, coerce_or_reject

if TYPE_CHECKING:
    from src.agents.recon import SiteProfile

_GENERATED_DIR = Path(__file__).resolve().parents[2] / "skills" / "_generated"


class RuleBasedSkillGenerator:
    """Heuristic generator — the deterministic bootstrap/fallback.

    It maps known coverage gaps (from recon) to spec templates. It is deliberately
    narrow: a real, general generator is the Claude reasoner. Without it the loop
    still closes for gaps the heuristic recognizes, which keeps the system useful
    with no API key."""

    def propose(self, profile: "SiteProfile", existing_cards: list[dict]) -> list[dict]:
        proposals: list[dict] = []
        for gap in profile.gaps:
            if gap.get("category") == "crawler-policy-disclosure":
                proposals.append({
                    "category": "crawler-policy-disclosure",
                    "action_type": "reconnaissance",
                    "risk_level": 1,
                    "severity": "low",
                    "name": "robots.txt path disclosure",
                    "title": "robots.txt discloses sensitive paths",
                    "tags": ["recon", "robots", "information-disclosure"],
                    "probes": [{"path": gap.get("path", "/robots.txt")}],
                    "detect": {"mode": "all", "conditions": [
                        {"check": "status_equals", "value": 200},
                        {"check": "body_contains", "substring": "Disallow"},
                    ]},
                    "source": "heuristic-generated",
                })
        return proposals


def generate_skills(
    reasoner,
    profile: "SiteProfile",
    *,
    allowed_testing: set[str],
    existing_specs: list[SkillSpec] = (),
    existing_cards: list[dict] = (),
) -> list[SkillSpec]:
    """Reasoner proposals -> validated, deduped, runnable SkillSpecs."""
    raw = reasoner.propose(profile, list(existing_cards))
    coerced = [coerce_or_reject(p, allowed_testing=allowed_testing) for p in raw]
    coerced = [s for s in coerced if s is not None]
    return dedupe_specs(coerced, existing_specs=existing_specs, existing_skill_cards=existing_cards)


def save_generated_spec(spec: SkillSpec, directory=None) -> Path:
    """Persist a generated spec (idempotent by id). Returns the path."""
    directory = Path(directory) if directory else _GENERATED_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{spec.id}.json"
    path.write_text(json.dumps(spec.to_record(), indent=2, sort_keys=True))
    return path


def load_generated_specs(directory=None) -> list[SkillSpec]:
    """Load previously-generated specs (the grown part of the library)."""
    directory = Path(directory) if directory else _GENERATED_DIR
    if not directory.is_dir():
        return []
    specs: list[SkillSpec] = []
    for path in sorted(directory.glob("*.json")):
        try:
            specs.append(SkillSpec.from_record(json.loads(path.read_text())))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue  # skip malformed; never crash the run on a bad generated file
    return specs
