import pytest

from src.agents import Planner
from src.agents.contracts import EngagementState
from src.agents.reasoners import RuleBasedPlanner
from src.authorization import (
    AuthorizationError,
    AuthorizationGuard,
    AuthorizationRegistry,
    StaticFingerprinter,
)
from src.memory.store import MemoryStore
from src.orchestrator import Orchestrator, build_orchestrator
from src.risk import RiskEngine
from src.scoring import Scorer
from src.skills.registry import SkillRegistry
from src.tools.http_client import fake_juice_shop_fetch

REGISTRY = "authorizations/authorized-targets.json"


def _orch_with_fingerprint(ok: bool) -> Orchestrator:
    store = MemoryStore(":memory:")
    risk_engine = RiskEngine()
    guard = AuthorizationGuard(
        AuthorizationRegistry.load(REGISTRY), risk_engine,
        fingerprinter=StaticFingerprinter(ok=ok, detail="test"),
    )
    return Orchestrator(
        store=store, guard=guard, risk_engine=risk_engine,
        skill_registry=SkillRegistry.with_defaults(), scorer=Scorer(store.conn),
        fetch=fake_juice_shop_fetch, rate_sleep=lambda _s: None,
    )


# ------------------------------------------------------------------- run_cycle
def test_full_cycle_closes_the_loop():
    orch = build_orchestrator(dry_run=True)
    report = orch.run_cycle("local-juice-shop", "assess")

    assert report.blocked_reason is None
    assert report.action is not None
    assert report.verdict.has_signal is True
    assert report.verdict.finding is not None
    assert report.finding_written is True
    pinned = next(b for b in report.context_blocks if b["region"] == "pinned")
    assert "local-juice-shop" in pinned["text"]
    assert orch.scorer.stats(report.action.skill_id).runs == 1


def test_unknown_authorization_fails_closed():
    orch = build_orchestrator(dry_run=True)
    with pytest.raises(AuthorizationError):
        orch.run_cycle("not-authorized", "x")


class _RecordingPlanner:
    def __init__(self) -> None:
        self.states: list[EngagementState] = []
        self._inner = RuleBasedPlanner()

    def propose(self, state: EngagementState):
        self.states.append(state)
        return self._inner.propose(state)


def test_metrics_feed_back_into_planning_across_cycles():
    # Discriminating test for "continuously learn": cycle 2's planner must see
    # cycle 1's accumulated metrics for the skill that actually ran.
    store = MemoryStore(":memory:")
    risk_engine = RiskEngine()
    guard = AuthorizationGuard(AuthorizationRegistry.load(REGISTRY), risk_engine,
                               fingerprinter=StaticFingerprinter(ok=True))
    recorder = _RecordingPlanner()
    orch = Orchestrator(store=store, guard=guard, risk_engine=risk_engine,
                        skill_registry=SkillRegistry.with_defaults(), scorer=Scorer(store.conn),
                        fetch=fake_juice_shop_fetch, planner=Planner(reasoner=recorder),
                        rate_sleep=lambda _s: None)

    r1 = orch.run_cycle("local-juice-shop", "g")
    orch.run_cycle("local-juice-shop", "g")
    ran = r1.action.skill_id

    def runs_for(state, skill_id):
        return next(s.runs for s in state.available_skills if s.skill_id == skill_id)

    assert runs_for(recorder.states[0], ran) == 0
    assert runs_for(recorder.states[1], ran) == 1
    assert orch.scorer.stats(ran).runs == 2


# -------------------------------------------------------------- run_engagement
def test_engagement_finds_real_issues_and_dedups():
    orch = build_orchestrator(dry_run=True)
    r1 = orch.run_engagement("local-juice-shop", "assess")

    assert r1.identity_ok is True
    assert len(r1.skill_outcomes) == 5          # all registered skills attempted
    assert all(o["ran"] for o in r1.skill_outcomes)
    assert len(r1.findings) >= 1                 # success criterion: >=1 finding
    assert all(f["new"] for f in r1.findings)
    # success criterion: at least one safe-active (risk >= 2) skill actually ran,
    # i.e. the risk gate was meaningfully exercised, not just risk-1 checks.
    assert any(o["ran"] and orch.skills.get(o["skill_id"]).risk_level >= 2 for o in r1.skill_outcomes)

    r2 = orch.run_engagement("local-juice-shop", "assess")
    assert sum(1 for f in r2.findings if f["new"]) == 0   # dedup holds on rerun

    distinct = orch.store.conn.execute(
        "SELECT COUNT(*) AS c FROM semantic_items WHERE kind='finding'"
    ).fetchone()["c"]
    assert distinct == len(r1.findings)


def test_engagement_fails_closed_on_identity_mismatch():
    orch = _orch_with_fingerprint(ok=False)
    with pytest.raises(AuthorizationError):
        orch.run_engagement("local-juice-shop", "assess")
