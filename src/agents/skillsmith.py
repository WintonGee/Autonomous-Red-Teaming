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
from typing import TYPE_CHECKING, Optional

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
    semantic_deduper=None,
    audit: Optional[dict] = None,
) -> list[SkillSpec]:
    """Reasoner proposals -> validated, deduped, runnable SkillSpecs.

    Dedupe layers applied here: structural/capability (always), then an optional
    *semantic* layer (`semantic_deduper`) that catches functional duplicates the
    structural layers miss — e.g. an LLM re-deriving an existing check under a
    different category. If `audit` is given it records every drop, so silent
    losses are visible (a self-improving system wants to know what it discarded)."""
    raw = reasoner.propose(profile, list(existing_cards))
    valid = [s for s in (coerce_or_reject(p, allowed_testing=allowed_testing) for p in raw) if s is not None]
    structural = dedupe_specs(valid, existing_specs=existing_specs, existing_skill_cards=existing_cards)

    unique = structural
    if semantic_deduper is not None and structural:
        redundant = set(semantic_deduper.redundant(structural, list(existing_cards)))
        unique = [s for i, s in enumerate(structural) if i not in redundant]
    if audit is not None:
        audit.update({
            "proposed": len(raw),
            "rejected_unsafe": len(raw) - len(valid),
            "dropped_duplicate": len(valid) - len(structural),
            "dropped_semantic": len(structural) - len(unique),
            "created": len(unique),
        })
    return unique


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
