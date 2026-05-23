# Orchestration Layer — the continuous-learning loop

A multi-agent system built on the [memory layer](memory/README.md). The
orchestrator sequences cooperating agents around shared memory and enforces the
charter's safety gates.

## Honest scope

**The loop's machinery, the safety gates, and the LLM brains are all real and
tested.** When `ANTHROPIC_API_KEY` is set, Claude-backed reasoners drive the
Planner, Evaluator, and Learner; otherwise deterministic rule-based reasoners run
— and those same rule-based reasoners are the fallback whenever an LLM call
errors. Either way the LLM only *proposes*: the Guard and RiskEngine gate every
action in code, and LLM-discovered findings are persisted as `pending_review`,
never auto-trusted.

**The self-improvement loop is now closed and measured.** Five safe web skills
ship (risk ≤2). End-of-engagement distillation (`memory/distill.py`) reads the
episodic finding log and proposes a reusable, human-reviewed skill for any
finding-category with no covering skill — so an issue the LLM Evaluator surfaces
in a category we lack becomes a skill the next run rediscovers deterministically.
A measurement harness (`src.measure`) scores each run against a ground-truth list
(`groundtruth/juice-shop.json`) and appends to `measurements/trend.tsv`, so
improvement over time is a number, not a claim. Current baseline: **100%
rediscovery (5/5) live against the Juice Shop lab.**

The honest caveat: with five skills the deterministic distiller no-ops (every
finding is already covered) — its value shows only once the LLM Evaluator
surfaces an *uncovered-category* finding. The "L" in this learning loop is still
the LLM. Remaining depth work: a report writer, embedding/semantic dedup, and the
human-approval gate for risk 3+.

## The cycle

```
authorize target (fail closed)
  └─ fresh working memory, pinned with authorization/scope/risk
      └─ Planner   → ProposedAction   (reads each skill's accumulated metrics)
          └─ Guard + RiskEngine        (fail closed; deterministic code)
              └─ Executor → ExecutionResult (scoped HttpClient; tool-layer scope check too)
                  └─ Evaluator → Verdict     (signal? finding? failure reason?)
                      └─ persist finding (deduped, authorization-scoped; logged to episodic)
                          └─ Learner → SkillProposals (reuse before create)
                              └─ Scorer.record  (persists → shapes next cycle)
                                  └─ distill_engagement → skill proposals (pending_review)
```

Run `python -m src.measure --live` to score an engagement against ground truth.

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
| `agents/` | Planner, Executor, Evaluator, Learner | Planner/Eval/Learner: Claude when `ANTHROPIC_API_KEY` set, else deterministic |
| `scoring/` | Per-skill metrics over time | no |
| `measure.py` | Rediscovery rate vs ground truth; writes trend | no |
| `memory/distill.py` | Episodic findings → proposed skills (pending review) | no |
| `orchestrator.py` | Sequences the loop, enforces gates | no |

Agent brains are injected via the Protocols in `agents/contracts.py`
(`PlannerReasoner`, `EvaluatorReasoner`, `LearnerReasoner`). Defaults are
deterministic; an LLM reasoner is a drop-in.

## Run it

```bash
python -m src.orchestrator --authorization local-juice-shop --goal assess
python -m src.orchestrator --cycles 2      # watch metrics accumulate across cycles
python -m src.orchestrator --live          # real requests (needs Juice Shop on :3001)
python -m src.measure                      # offline rediscovery vs ground truth
python -m src.measure --live               # measure against the live lab
export ANTHROPIC_API_KEY=...               # activates the Claude reasoners (else deterministic)
pytest                                       # full suite, no network or API key required
```

## Deliberately not built yet

A report writer (findings → human-readable report), embedding/semantic dedup
(`sqlite-vec`), and the human-approval gate for risk level 3+. (LLM reasoners,
evidence redaction, the 5-skill library, end-of-engagement distillation, and the
measurement harness are now built.) The next highest-leverage move is the report
writer — every finding currently lives as JSON.
