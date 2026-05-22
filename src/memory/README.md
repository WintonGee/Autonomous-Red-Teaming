# Memory & Context Layer

The substrate that lets a long-running agent work without drowning in its own
output. It implements the README's **Deduplication Engine** and the memory the
**Learning Loop** depends on.

## Core idea: context ≠ memory

The model's context window is a **working set** (a cache), not memory. Durable
memory lives outside the model in SQLite. "Context management" is deciding what
to load into the working set and when to flush it.

## Tiers

| Tier | Holds | Lifetime | Where | Module |
|---|---|---|---|---|
| Working memory | What the model sees now | Ephemeral, token-budgeted | in-context | `context.py` |
| Episodic memory | Event log of one engagement | Per-engagement | SQLite | `store.py` |
| Semantic memory | Skills, findings, patterns | Permanent | SQLite (+vec) | `store.py` |
| Evidence | Raw blobs, never in context | Permanent | filesystem | `evidence_refs` |

## Self-clearing, three ways

1. **Session boundary** (`session.start_engagement`) — every engagement gets a
   *fresh* working memory seeded with pinned facts + authorization-scoped
   knowledge. Junk never leaks across tasks.
2. **Ephemeral TTL** (`ephemeral_ttl_turns`) — items tagged `ephemeral` (raw
   tool output, dead-end reasoning) auto-clear after N further adds, *regardless
   of budget*. Scratch tagged as junk actually behaves like junk.
3. **Compaction** (`WorkingMemory.compact`) — within a run, budget overflow
   triggers: drop ephemeral → fold old salient into a rolling summary → keep the
   recent window verbatim.

## Safety invariants

- **Pinned facts never evicted.** Authorization, scope, risk limits, and goal
  are pinned; compaction cannot remove them.
- **Fail closed on render.** `render()` raises `PinnedContextMissing` if no
  pinned facts are present — a context with no authorization is never sent to a
  model.
- **Authorization scoping.** `retrieve_semantic` only returns the engagement's
  own items plus global (NULL) items. A finding from target X cannot enter
  target Y's context.

## Deduplication (phase 1: exact)

Normalize (trim/lowercase/collapse whitespace) → SHA-256. Three places use it,
with distinct jobs:

- **Write-time** — `store.add_event(deduplicate=True)` skips re-inserting content
  already seen *in the same engagement* (per-engagement scope), returning the
  original event id. Use for repeated tool output you don't want stored twice.
- **Registry** — `ExactDeduplicator` is the shared content-seen index over
  `dedup_hashes` for arbitrary scopes. Use it to ask "have I seen this before?"
  *before* doing expensive work, without inserting an event.
- **Sweep-time** — `gc.run_gc` evicts expired ephemeral events and collapses
  exact duplicates as a safety net for rows inserted with `deduplicate=False`.

Phase 2 (embedding near-dup) will use the reserved `embedding` column.

## Production wiring (injection points)

- **Token counting** — pass Anthropic's tokenizer:
  `WorkingMemory(count_tokens=lambda t: client.messages.count_tokens(...).input_tokens)`
- **Summarizer** — pass an LLM-backed summarizer instead of the truncating default.
- **Prompt caching** — `render()` marks the stable preamble `cacheable=True`;
  apply `cache_control` to those blocks.

## Not built yet (seams)

- `distill.py` — the learning loop (episodic → proposed skills → review →
  semantic). Raises `NotImplementedError`; needs the AI planning layer.
- Semantic dedup / vector retrieval — needs `sqlite-vec` + embeddings.

## Run the tests

```bash
pip install -r requirements.txt
pytest
```
