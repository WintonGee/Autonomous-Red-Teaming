"""Deterministic, offline reasoners — the default "brains".

They make the loop close and the gates testable without any LLM. Each implements
one of the Protocols in contracts.py, so an Anthropic-backed reasoner is a
drop-in replacement. The Learner is the highest-leverage place to add a real LLM
(it can currently only dedup, not invent); that is the named next milestone.
"""
from __future__ import annotations

from typing import Optional

from .contracts import (
    EngagementState,
    ExecutionResult,
    ProposedAction,
    SkillInfo,
    SkillProposal,
    Verdict,
)


class RuleBasedPlanner:
    def propose(self, state: EngagementState) -> Optional[ProposedAction]:
        candidates = [s for s in state.available_skills if s.risk_level <= state.max_risk]
        if not candidates:
            return None
        # Highest yield first; among ties, explore the least-run skill. This is
        # where past metrics shape future behavior (the "improvement" feedback).
        candidates.sort(key=lambda s: (-s.signal_ratio, s.runs, s.skill_id))
        best = candidates[0]
        return ProposedAction(
            skill_id=best.skill_id,
            target_url=state.target_url,
            action_type=best.action_type,
            risk_level=best.risk_level,
            rationale=(
                f"Selected {best.skill_id} (signal_ratio={best.signal_ratio:.2f}, "
                f"runs={best.runs}) for goal {state.goal!r}."
            ),
        )


class RuleBasedEvaluator:
    def evaluate(self, result: ExecutionResult) -> Verdict:
        if not result.ok:
            return Verdict(
                action=result.action,
                has_signal=False,
                confidence="none",
                failure_reason=result.error,
                rationale="Execution failed; no evaluation possible.",
            )
        missing = result.observations.get("missing_headers") or []
        if missing:
            finding = {
                "title": f"Missing security headers: {', '.join(missing)}",
                "category": "web-misconfiguration",
                "severity": "low",
                "confidence": "confirmed",
                "skill_id": result.action.skill_id,
                "target": result.action.target_url,
                "evidence": {
                    "status_code": result.observations.get("status_code"),
                    "missing_headers": missing,
                },
            }
            return Verdict(
                action=result.action,
                has_signal=True,
                confidence="confirmed",
                finding=finding,
                rationale=f"Confirmed {len(missing)} missing security header(s).",
            )
        return Verdict(
            action=result.action,
            has_signal=False,
            confidence="none",
            rationale="No missing security headers detected.",
        )


class RuleBasedLearner:
    def propose_skills(
        self, verdicts: list[Verdict], existing: list[SkillInfo]
    ) -> list[SkillProposal]:
        # Reuse before create: if the finding came from a skill we already have,
        # propose nothing. A real (LLM) learner would generalize patterns here.
        existing_ids = {s.skill_id for s in existing}
        proposals: list[SkillProposal] = []
        for v in verdicts:
            if v.finding and v.action.skill_id not in existing_ids:
                proposals.append(
                    SkillProposal(
                        title=f"Detect {v.finding.get('category', 'unknown')}",
                        category=v.finding.get("category", "unknown"),
                        rationale="Finding has no covering skill.",
                        payload={"seed_finding": v.finding},
                    )
                )
        return proposals
