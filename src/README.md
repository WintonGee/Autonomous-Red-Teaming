# Orchestration Layer — the continuous-learning loop

A multi-agent system built on the [memory layer](memory/README.md). The
orchestrator sequences cooperating agents around shared memory and enforces the
charter's safety gates.

## Honest scope

**This proves the loop's machinery and the safety gates — not yet genuine skill
generation.** With deterministic agents and one skill, the Learner can only
*dedup* (reuse before create) and the Planner has one option to prioritize. The
architecture, gates, memory wiring, and the feedback mechanism are real and
tested. The *intelligence* arrives when each agent's reasoner is wired to Claude.

**Immediate next milestone: wire the Learner to Claude** — it is the one agent
that needs an LLM to do anything beyond dedup (generalize new detection patterns
from confirmed findings and failures). Planner and Evaluator can stay
deterministic longer. Use the `claude-api` skill for SDK + prompt-caching
mechanics; implement `LearnerReasoner` against the Anthropic SDK and pass it to
`Learner(reasoner=...)`. No other file changes.

## The cycle

```
authorize target (fail closed)
  └─ fresh working memory, pinned with authorization/scope/risk
      └─ Planner   → ProposedAction   (reads each skill's accumulated metrics)
          └─ Guard + RiskEngine        (fail closed; deterministic code)
              └─ Executor → ExecutionResult (scoped HttpClient; tool-layer scope check too)
                  └─ Evaluator → Verdict     (signal? finding? failure reason?)
                      └─ persist finding (deduped, authorization-scoped)
                          └─ Learner → SkillProposals (reuse before create)
                              └─ Scorer.record  (persists → shapes next cycle)
```

## Why it "continuously improves"

`Scorer` writes every run to `skill_runs` in the same SQLite DB. The next
cycle's `Planner` reads those stats (`signal_ratio`, `runs`) to prioritize
skills. Run against the learning lab (known vulns) this becomes measurable:
rediscovery rate and signal ratio over time. The two-cycle test
(`tests/agents/test_orchestrator_cycle.py`) asserts the feedback path executes
end to end.

## Components

| Module | Role | LLM? |
|---|---|---|
| `authorization/` | Registry + Guard — what may be tested | no (deterministic) |
| `risk/` | Risk levels + ceiling enforcement | no |
| `tools/` | Gated HTTP client (refuses unauthorized URLs itself) | no |
| `skills/` | Detection logic (pure; no I/O) | no |
| `agents/` | Planner, Executor, Evaluator, Learner | Planner/Eval/Learner: swappable |
| `scoring/` | Per-skill metrics over time | no |
| `orchestrator.py` | Sequences the loop, enforces gates | no |

Agent brains are injected via the Protocols in `agents/contracts.py`
(`PlannerReasoner`, `EvaluatorReasoner`, `LearnerReasoner`). Defaults are
deterministic; an LLM reasoner is a drop-in.

## Run it

```bash
python -m src.orchestrator --authorization local-juice-shop --goal missing-headers
python -m src.orchestrator --cycles 2      # watch metrics accumulate across cycles
python -m src.orchestrator --live          # real requests (needs Juice Shop on :3000)
pytest                                       # full suite, no network required
```

## Deliberately not built yet

LLM reasoners, embedding/semantic dedup (`sqlite-vec`), multi-skill discovery,
report writer, evidence redaction. The thin slice's job is to close the loop
safely, not to be feature-complete.
