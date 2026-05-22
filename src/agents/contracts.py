"""Typed contracts shared across agents.

These dataclasses and Protocols are the stable interfaces between agents. Wiring
an LLM-backed brain later means implementing a Protocol (e.g. against the
Anthropic SDK) — not redesigning the agents. That is the whole point of locking
them now.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass
class SkillInfo:
    """A skill plus its accumulated performance — what the planner reasons over."""
    skill_id: str
    name: str
    category: str
    risk_level: int
    action_type: str
    runs: int = 0
    signal_ratio: float = 0.0


@dataclass
class EngagementState:
    authorization_id: str
    goal: str
    target_url: str
    available_skills: list[SkillInfo]
    max_risk: int


@dataclass
class ProposedAction:
    skill_id: str
    target_url: str
    action_type: str
    risk_level: int
    rationale: str
    params: dict = field(default_factory=dict)


@dataclass
class ExecutionResult:
    action: ProposedAction
    ok: bool
    observations: dict = field(default_factory=dict)
    evidence_ref: Optional[int] = None
    error: Optional[str] = None


@dataclass
class Verdict:
    action: ProposedAction
    has_signal: bool
    confidence: str  # confirmed | suspected | none
    finding: Optional[dict] = None
    failure_reason: Optional[str] = None
    rationale: str = ""
    extra_findings: list = field(default_factory=list)  # LLM-discovered, pending review


@dataclass
class SkillProposal:
    title: str
    category: str
    rationale: str
    payload: dict = field(default_factory=dict)


@runtime_checkable
class PlannerReasoner(Protocol):
    def propose(self, state: EngagementState) -> Optional[ProposedAction]: ...


@runtime_checkable
class EvaluatorReasoner(Protocol):
    def evaluate(self, result: ExecutionResult) -> Verdict: ...


@runtime_checkable
class LearnerReasoner(Protocol):
    def propose_skills(
        self, verdicts: list[Verdict], existing: list[SkillInfo]
    ) -> list[SkillProposal]: ...
