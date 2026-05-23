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

**The self-improvement loop is now closed and measured.** A library of safe web
skills (risk ≤2) ships. End-of-engagement distillation (`memory/distill.py`) reads the
episodic finding log and proposes a reusable, human-reviewed skill for any
finding-category with no covering skill — so an issue the LLM Evaluator surfaces
in a category we lack becomes a skill the next run rediscovers deterministically.
A measurement harness (`src.measure`) scores each run against a ground-truth list
(`groundtruth/juice-shop.json`) and appends to `measurements/trend.tsv`, so
improvement over time is a number, not a claim. The system rediscovers every
ground-truth issue it has a skill for; ground truth also lists known *coverage
gaps* (issues with no skill yet, e.g. `js-robots-disclosure`) so the rate stays
honestly below 100% and names the next skill to build — the metric tracks real
capability, not a checklist scoring itself.

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

## Fully autonomous mode (`run_autonomous`)

Point it at an authorized target and it runs the whole loop itself:

```
authorize + fingerprint
  └─ Recon      → SiteProfile  (understanding + plan + coverage gaps)   [LLM or heuristic]
      └─ try the existing arsenal (trusted skills + prior-generated specs)
          └─ Skillsmith → new SkillSpecs for the gaps                   [LLM or heuristic]
              └─ coerce_or_reject (trust boundary) + 5-layer dedupe
                  └─ run the new specs (gated, risk ≤2) → pending_review findings
                      └─ persist specs to skills/_generated/ (library grows)
                          └─ score + distill
```

**New skills are data, not code.** A generated skill is a declarative `SkillSpec`
(probes + a closed set of typed detect conditions) executed by the trusted
`SpecSkill` interpreter — the LLM authors specs, it never runs arbitrary code, and
`coerce_or_reject` enforces risk ≤2, GET-only, authorized action types, and safe
paths/patterns. Generated specs persist under `skills/_generated/` and rejoin the
arsenal next run, so the library genuinely grows; promotion into the trusted
`skills/` set stays a human decision.

**Dedupe (5 layers):** prompt-level (the generator sees the catalog) → capability
signature (category+action_type+tags) → structural spec signature (order-
insensitive, normalized probes+conditions) → within-batch → content-hash at
persistence. Demonstrated live: run 2 reuses the run-1 generated skill instead of
recreating it.

```bash
python -m src.autonomous --live            # understand → try → create → dedupe → score
python -m src.autonomous --live --use-llm  # LLM recon + LLM skill generation
# a second, external, vendor-sanctioned target (HCL AppScan's "Altoro Mutual"):
python -m src.autonomous --live --authorization altoro-mutual --groundtruth groundtruth/none.json
```

### Picking a target you're allowed to scan

Authorization is the point, so the registry only holds targets you may test:
self-hosted vulnerable apps (Juice Shop) and **vendor-published test sites that
explicitly permit scanning** (`demo.testfire.net`, the `*.vulnweb.com` family).
A site being reachable or "for hackers" does **not** make it a valid target —
e.g. hackthissite.org's *challenges* are the sanctioned playground, its
*infrastructure* is not; it is deliberately absent from the registry.

**Cross-target honesty:** run against AltoroMutual, the generic header-based
skills (missing-headers, info-disclosure) generalize and find real issues, while
the Juice-Shop-tuned skills (`exposed_sensitive_paths`, `verbose_errors`) probe
Juice-Shop paths and correctly find nothing. That gap is by design: probe lists
are *not* hardcoded to be universal — adapting to a new target is the job of the
LLM recon (`ClaudeRecon`) and skill generator (`ClaudeSkillGenerator`), which
author target-appropriate skills per site.

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
| `agents/recon.py` | Gather + understand a target → SiteProfile | Claude or heuristic |
| `agents/skillsmith.py` | Generate + dedupe new SkillSpecs | Claude or heuristic |
| `skills/spec.py` | Declarative spec schema, trust boundary, safe interpreter | no |
| `memory/distill.py` | Episodic findings → proposed skills (pending review) | no |
| `autonomous.py` | Point-and-go: understand → try → create → dedupe → score | no |
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
(`sqlite-vec`), LLM-directed crawling (recon currently fetches a fixed safe set,
not an LLM-chosen frontier), and active testing at risk 3 behind the human-
approval gate. (LLM reasoners, evidence redaction, the skill library, distillation,
the measurement harness, and the fully-autonomous generate-and-dedupe loop are
built.) The next highest-leverage move is the report writer — findings still live
as JSON.
