# Skill Library

The AI-facing catalog of skills. Each `*.json` here is a **knowledge card** the
LLM/agent references to decide *what* a skill is, *when* to use it, *how* it
detects, and *where the public references are*.

## Layers (no duplication by design)

| Layer | Holds | Where |
|---|---|---|
| Execution | code + governance metadata (`id, name, category, risk_level, action_type, target_types, tool`) and `run()` | `src/skills/**/*.py` |
| Knowledge | `id` + `purpose, when_to_use, detection_approach, references[], tags, status` | `skills/**/*.json` (here) |
| Runtime memory | retrieval index, authorization-scoped | SQLite `semantic_items` |

The two file layers share **only `id`** — disjoint fields, so there is nothing
to drift. `SkillLibrary` (`src/skills/library.py`) composes them into the full
card the agent references.

## Honest scope

These cards are LLM-*readable*, but **no LLM reads them yet**. Today the agents
are deterministic; the planner/learner consulting these cards (and LLM-backed
research to fill new ones) is the next milestone. This folder is the substrate,
not the closed loop.

## Drafts (`_drafts/`)

Proposed skills from the research seam land in `_drafts/` with
`status: pending_review` and `implementation: null` — they **cannot run**. The
library loader explicitly refuses to load anything under `_drafts/` (and skips
any non-`active` card), so an unreviewed draft can never become a live skill
without human promotion. Draft contents are gitignored.

## Deduplication

`src/skills/dedup.py` keeps the library from bloating: a new card is rejected as
a duplicate if it shares an `id` or a capability signature (category +
action_type + sorted tags) with an existing skill — "reuse before create".
Exact only for now; semantic near-duplicate detection (embeddings) is Phase 2,
matching the memory layer's dedup story.

## Inspect

```bash
python -m src.skills.library            # list composed cards
python -m src.skills.library --dedup    # report duplicate/near-duplicate skills
python -m src.skills.library --gaps web-misconfiguration,sql-injection
```
