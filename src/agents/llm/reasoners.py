"""Claude-backed reasoners — the non-deterministic brains.

Each implements the same Protocol as its rule-based counterpart and holds a
deterministic fallback used when the client is unavailable or the call errors.
The LLM only *proposes*; the orchestrator's Guard/RiskEngine still gate every
action, and LLM-discovered findings are persisted as pending_review (never
auto-trusted).

Cost shape: an engagement makes one Evaluator call per skill that ran, plus one
Learner call — i.e. N+1 model calls for N eligible skills. Cheap at today's two
skills (~3 Opus calls); watch this as the skill library grows.
"""
from __future__ import annotations

import json
from typing import Optional

from src.agents.contracts import (
    EngagementState,
    EvaluatorReasoner,
    ExecutionResult,
    LearnerReasoner,
    PlannerReasoner,
    ProposedAction,
    SkillInfo,
    SkillProposal,
    Verdict,
)
from src.agents.llm.client import ClaudeClient, LlmError
from src.agents.llm.redact import redact

_MAX_LLM_FINDINGS = 3


class ClaudePlanner:
    """Picks which skill to run. The LLM chooses skill_id + rationale only;
    the target URL stays fixed in code (the gate would catch a bad URL, but we
    don't even let the model propose one)."""

    def __init__(self, client: ClaudeClient, fallback: PlannerReasoner) -> None:
        self.client = client
        self.fallback = fallback

    def propose(self, state: EngagementState) -> Optional[ProposedAction]:
        eligible = [s for s in state.available_skills if s.risk_level <= state.max_risk]
        if not eligible or not self.client.available():
            return self.fallback.propose(state)
        by_id = {s.skill_id: s for s in eligible}
        tool = {
            "name": "choose_skill",
            "description": "Choose the most useful skill to run next for the goal.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string", "enum": list(by_id)},
                    "rationale": {"type": "string"},
                },
                "required": ["skill_id", "rationale"],
                "additionalProperties": False,
            },
        }
        catalog = [
            {"skill_id": s.skill_id, "category": s.category, "risk_level": s.risk_level,
             "runs": s.runs, "signal_ratio": round(s.signal_ratio, 2)}
            for s in eligible
        ]
        user = (
            f"Goal: {state.goal}\nTarget: {state.target_url}\n"
            f"Available skills (risk <= {state.max_risk}):\n{json.dumps(catalog, indent=2)}\n"
            "Choose the single best skill to run next."
        )
        try:
            result = self.client.structured(
                system="You are a security test planner. Pick one skill from the provided list.",
                user=user, tool=tool, tool_name="choose_skill",
                audit_meta={"agent_role": "planner", "chars_sent": len(user)},
            )
            skill = by_id.get(result.get("skill_id"))
            if skill is None:  # model picked something not on the menu -> fail safe
                return self.fallback.propose(state)
            return ProposedAction(
                skill_id=skill.skill_id, target_url=state.target_url,
                action_type=skill.action_type, risk_level=skill.risk_level,
                rationale=f"[claude] {result.get('rationale', '')}".strip(),
            )
        except LlmError:
            return self.fallback.propose(state)


class ClaudeEvaluator:
    """Keeps the skill's deterministic finding as the trusted primary, and adds
    LLM-discovered issues the fixed rule didn't encode. The LLM selects findings
    by pointing at a key in an evidence index; code resolves the pointer back to
    real bytes and drops anything that doesn't resolve (no invented evidence)."""

    def __init__(self, client: ClaudeClient, fallback: EvaluatorReasoner) -> None:
        self.client = client
        self.fallback = fallback

    def evaluate(self, result: ExecutionResult) -> Verdict:
        verdict = self.fallback.evaluate(result)  # trusted, deterministic primary
        if not result.ok or not self.client.available():
            return verdict

        index = _evidence_index(result.observations)
        if not index:
            return verdict
        redacted, secrets = _redact_index(index)
        tool = {
            "name": "report_findings",
            "description": "Report security issues evidenced ONLY by the provided index.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "rationale": {"type": "string"},
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "category": {"type": "string"},
                                "severity": {"type": "string", "enum": ["info", "low", "medium", "high"]},
                                "evidence_pointer": {"type": "string"},
                            },
                            "required": ["title", "category", "severity", "evidence_pointer"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["rationale", "findings"],
                "additionalProperties": False,
            },
        }
        user = (
            f"Skill {result.action.skill_id} ran against {result.action.target_url}.\n"
            "Evidence index (cite an issue ONLY by one of these exact keys):\n"
            f"{json.dumps(redacted, indent=2)}\n"
            "List security issues a fixed checklist might miss (info disclosure, errors, "
            "tokens, odd redirects). Use only evidence_pointer values from the index keys."
        )
        try:
            out = self.client.structured(
                system="You are a security evidence reviewer. Never invent evidence; cite index keys only.",
                user=user, tool=tool, tool_name="report_findings",
                audit_meta={"agent_role": "evaluator", "chars_sent": len(user),
                            "redacted_secrets": secrets},
            )
        except LlmError:
            return verdict

        for item in (out.get("findings") or [])[:_MAX_LLM_FINDINGS]:
            pointer = item.get("evidence_pointer")
            if pointer not in index:  # unresolved pointer -> drop (anti-hallucination)
                continue
            verdict.extra_findings.append({
                "title": item.get("title", "Unspecified issue"),
                "category": item.get("category", "unknown"),
                "severity": item.get("severity", "info"),
                "confidence": "suspected",
                "source": "llm-evaluator",
                "skill_id": result.action.skill_id,
                "target": result.action.target_url,
                "evidence": {"pointer": pointer, "value": index[pointer][:500]},
            })
        if verdict.extra_findings:
            verdict.has_signal = True
            verdict.rationale = (verdict.rationale + " | " + out.get("rationale", "")).strip(" |")
        return verdict


class ClaudeLearner:
    """Proposes new skills generalized from confirmed findings (reuse before
    create is enforced downstream by the skills-library dedup). Proposals become
    human-reviewed drafts; nothing auto-runs."""

    def __init__(self, client: ClaudeClient, fallback: LearnerReasoner) -> None:
        self.client = client
        self.fallback = fallback

    def propose_skills(self, verdicts: list[Verdict], existing: list[SkillInfo]) -> list[SkillProposal]:
        base = self.fallback.propose_skills(verdicts, existing)
        findings = [v.finding for v in verdicts if v.finding]
        for v in verdicts:
            findings.extend(v.extra_findings)
        if not findings or not self.client.available():
            return base

        existing_categories = sorted({s.category for s in existing})
        tool = {
            "name": "propose_skills",
            "description": "Propose reusable detection skills generalized from findings.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "proposals": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "category": {"type": "string"},
                                "rationale": {"type": "string"},
                            },
                            "required": ["title", "category", "rationale"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["proposals"],
                "additionalProperties": False,
            },
        }
        summary = [{"title": f.get("title"), "category": f.get("category")} for f in findings]
        user = (
            f"Confirmed/suspected findings:\n{json.dumps(summary, indent=2)}\n"
            f"Existing skill categories (do not duplicate): {existing_categories}\n"
            "Propose at most 3 NEW reusable detection skills for gaps these reveal."
        )
        try:
            out = self.client.structured(
                system="You generalize security findings into reusable, non-duplicate detection skills.",
                user=user, tool=tool, tool_name="propose_skills",
                audit_meta={"agent_role": "learner", "chars_sent": len(user)},
            )
        except LlmError:
            return base

        proposals = list(base)
        for item in (out.get("proposals") or [])[:_MAX_LLM_FINDINGS]:
            category = item.get("category", "unknown")
            if category in existing_categories:  # reuse before create
                continue
            proposals.append(SkillProposal(
                title=item.get("title", "Proposed skill"),
                category=category,
                rationale=f"[claude] {item.get('rationale', '')}".strip(),
                payload={"source": "llm-learner"},
            ))
        return proposals


def _evidence_index(observations: dict) -> dict[str, str]:
    """Flatten observations into pointer_key -> string for citation/resolution."""
    index: dict[str, str] = {}
    for key, value in observations.items():
        if key == "finding":
            continue  # the skill's own finding is the trusted primary, handled elsewhere
        if isinstance(value, (str, int, float, bool)):
            index[key] = str(value)
        else:
            index[key] = json.dumps(value, default=str)
            if isinstance(value, list):
                for i, item in enumerate(value[:10]):
                    index[f"{key}[{i}]"] = json.dumps(item, default=str)
    return index


def _redact_index(index: dict[str, str]) -> tuple[dict[str, str], int]:
    redacted: dict[str, str] = {}
    total = 0
    for key, value in index.items():
        clean, n = redact(value)
        redacted[key] = clean
        total += n
    return redacted, total
