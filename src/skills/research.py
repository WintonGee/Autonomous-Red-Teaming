"""Research-and-create seam for missing skills (human-reviewed drafts).

When a capability is needed but no skill exists, this proposes a DRAFT skill
card for human review. It enforces reuse-before-create (dedup against the
library first) and writes drafts to skills/_drafts/ with status=pending_review
and implementation=null, so a draft can never run.

Today the draft is a template with the relevant fields stubbed for a human to
fill. LLM-backed research (searching OWASP/CWE/PortSwigger to populate
detection_approach + references) is the next milestone — this is the seam it
plugs into, not the closed loop.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from src.skills.dedup import find_duplicate
from src.skills.library import SkillLibrary

# Repo-relative, so drafts land in the library regardless of caller cwd.
_DRAFTS_DIR = Path(__file__).resolve().parents[2] / "skills" / "_drafts"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def propose_skill_card(
    *,
    capability: str,
    category: str,
    action_type: str,
    risk_level: int,
    tags: Optional[list[str]] = None,
    references: Optional[list[dict]] = None,
    library: Optional[SkillLibrary] = None,
    drafts_dir: Optional[str] = None,
) -> dict:
    """Propose a skill for a needed capability.

    Returns {"status": "reuse", "existing": <id>} if an equivalent skill exists,
    else {"status": "draft", "path": <file>, "card": <draft>} after writing a
    pending-review draft. The draft is never runnable (implementation=null).
    """
    library = library or SkillLibrary.load()
    candidate = {
        "id": f"draft.{_slug(capability)}",
        "category": category,
        "action_type": action_type,
        "tags": sorted(tags or []),
    }

    # Reuse before create.
    duplicate = find_duplicate(candidate, library.all())
    if duplicate is not None:
        return {"status": "reuse", "existing": duplicate.get("id")}

    draft = {
        "id": candidate["id"],
        "name": capability,
        "category": category,
        "risk_level": risk_level,
        "action_type": action_type,
        "target_types": ["web-application"],
        "tool": "http-client",
        "purpose": f"[DRAFT — human review required] {capability}",
        "when_to_use": "TODO (research): when this skill applies.",
        "detection_approach": "TODO (research): how detection works. To be populated by LLM-backed research and reviewed before implementation.",
        "references": references or [],
        "tags": candidate["tags"],
        "implementation": None,   # not implemented -> cannot run
        "status": "pending_review",
    }

    drafts_path = Path(drafts_dir) if drafts_dir else _DRAFTS_DIR
    drafts_path.mkdir(parents=True, exist_ok=True)
    out = drafts_path / f"{candidate['id']}.json"
    out.write_text(json.dumps(draft, indent=2, sort_keys=True))
    return {"status": "draft", "path": str(out), "card": draft}
