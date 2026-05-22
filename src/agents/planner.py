"""Planner agent: chooses the next action from scoped skills + their metrics."""
from __future__ import annotations

from typing import Optional

from .contracts import EngagementState, PlannerReasoner, ProposedAction
from .reasoners import RuleBasedPlanner


class Planner:
    def __init__(self, reasoner: Optional[PlannerReasoner] = None) -> None:
        self.reasoner: PlannerReasoner = reasoner or RuleBasedPlanner()

    def plan(self, state: EngagementState) -> Optional[ProposedAction]:
        return self.reasoner.propose(state)
