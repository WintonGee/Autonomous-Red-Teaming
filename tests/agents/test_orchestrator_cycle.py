import pytest

from src.agents import Planner
from src.agents.contracts import EngagementState, ProposedAction
from src.agents.reasoners import RuleBasedPlanner
from src.authorization import (
    AuthorizationError,
    AuthorizationGuard,
    AuthorizationRegistry,
)
from src.memory.store import MemoryStore
from src.orchestrator import Orchestrator, build_orchestrator
from src.risk import RiskEngine
from src.scoring import Scorer
from src.skills.registry import SkillRegistry
from src.tools.http_client import fake_juice_shop_fetch

REGISTRY = "authorizations/authorized-targets.json"


def test_full_cycle_closes_the_loop():
    orch = build_orchestrator(dry_run=True)
    report = orch.run_cycle("local-juice-shop", "missing-headers")

    assert report.blocked_reason is None
    assert report.action.skill_id == "web.missing_security_headers"
    assert report.verdict.has_signal is True
    assert report.verdict.finding is not None
    assert report.finding_written is True
    # Reuse before create: an existing skill covers this finding -> no proposals.
    assert report.proposals == []
    # Pinned authorization fact made it into the rendered context.
    pinned = next(b for b in report.context_blocks if b["region"] == "pinned")
    assert "local-juice-shop" in pinned["text"]
    # The run was scored.
    assert orch.scorer.stats("web.missing_security_headers").runs == 1


def test_unknown_authorization_fails_closed():
    orch = build_orchestrator(dry_run=True)
    with pytest.raises(AuthorizationError):
        orch.run_cycle("not-authorized", "x")


def test_finding_deduped_across_cycles():
    orch = build_orchestrator(dry_run=True)
    r1 = orch.run_cycle("local-juice-shop", "g")
    r2 = orch.run_cycle("local-juice-shop", "g")
    assert r1.finding_written is True
    assert r2.finding_written is False  # identical finding deduped on the second run
    count = orch.store.conn.execute(
        "SELECT COUNT(*) AS c FROM semantic_items WHERE kind='finding'"
    ).fetchone()["c"]
    assert count == 1


class _RecordingPlanner:
    """Wraps the rule-based planner and records the state it was given each cycle."""

    def __init__(self) -> None:
        self.states: list[EngagementState] = []
        self._inner = RuleBasedPlanner()

    def propose(self, state: EngagementState):
        self.states.append(state)
        return self._inner.propose(state)


def test_metrics_feed_back_into_planning_across_cycles():
    # This is the discriminating test for "continuously learn": the second
    # cycle's planner must see the first cycle's accumulated metrics.
    store = MemoryStore(":memory:")
    risk_engine = RiskEngine(project_ceiling=1)
    guard = AuthorizationGuard(AuthorizationRegistry.load(REGISTRY), risk_engine)
    recorder = _RecordingPlanner()
    orch = Orchestrator(
        store=store,
        guard=guard,
        risk_engine=risk_engine,
        skill_registry=SkillRegistry.with_defaults(),
        scorer=Scorer(store.conn),
        fetch=fake_juice_shop_fetch,
        planner=Planner(reasoner=recorder),
    )

    orch.run_cycle("local-juice-shop", "g")
    orch.run_cycle("local-juice-shop", "g")

    skill = "web.missing_security_headers"
    # Cycle 1 planned with no history; cycle 2 saw the first run's metrics.
    assert recorder.states[0].available_skills[0].runs == 0
    assert recorder.states[1].available_skills[0].runs == 1
    assert recorder.states[1].available_skills[0].signal_ratio == 1.0
    # Scorer state persisted across both cycles.
    assert orch.scorer.stats(skill).runs == 2
