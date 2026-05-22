"""Learner agent: turns verdicts into reviewed skill proposals (the loop's memory).

This is the highest-leverage place to wire a real LLM: the rule-based default can
only dedup against existing skills, while an LLM learner can generalize new
detection patterns from confirmed findings and failures.
"""
from __future__ import annotations

from typing import Optional

from .contracts import LearnerReasoner, SkillInfo, SkillProposal, Verdict
from .reasoners import RuleBasedLearner


class Learner:
    def __init__(self, reasoner: Optional[LearnerReasoner] = None) -> None:
        self.reasoner: LearnerReasoner = reasoner or RuleBasedLearner()

    def learn(self, verdicts: list[Verdict], existing: list[SkillInfo]) -> list[SkillProposal]:
        return self.reasoner.propose_skills(verdicts, existing)
