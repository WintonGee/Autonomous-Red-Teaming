import json

from src.agents import Evaluator
from src.agents.reasoners import RuleBasedEvaluator
from src.authorization import (
    AuthorizationGuard,
    AuthorizationRegistry,
    StaticFingerprinter,
)
from src.memory.distill import distill_engagement
from src.memory.store import MemoryStore
from src.orchestrator import Orchestrator, build_orchestrator
from src.risk import RiskEngine
from src.scoring import Scorer
from src.skills.registry import SkillRegistry
from src.tools.http_client import fake_juice_shop_fetch

REGISTRY = "authorizations/authorized-targets.json"


def _seed_skill(store, category):
    store.add_semantic_item(
        kind="skill", title=f"skill-{category}", external_id=f"web.{category}",
        content={"category": category}, tags=[category],
    )


def _add_finding_event(store, engagement_id, category, title="x"):
    store.add_event(
        engagement_id=engagement_id, authorization_id="a", event_type="finding",
        content=json.dumps({"title": title, "category": category}), salience="salient",
    )


def test_distill_proposes_for_uncovered_category():
    store = MemoryStore(":memory:")
    _seed_skill(store, "web-misconfiguration")
    _add_finding_event(store, "eng1", "open-redirect", "Open redirect via returnUrl")

    proposals = distill_engagement(store, "eng1")
    assert len(proposals) == 1
    assert proposals[0]["category"] == "open-redirect"
    assert proposals[0]["source"] == "distilled"


def test_distill_skips_already_covered_category():
    store = MemoryStore(":memory:")
    _seed_skill(store, "open-redirect")  # already have a skill for it
    _add_finding_event(store, "eng1", "open-redirect")

    assert distill_engagement(store, "eng1") == []


def test_distill_is_noop_when_all_findings_covered_by_real_skills():
    # The honest no-LLM case: every finding came from an existing skill, so every
    # category is covered and distillation correctly proposes nothing.
    orch = build_orchestrator(dry_run=True, llm=False)
    report = orch.run_engagement("local-juice-shop", "assess")
    assert report.distilled == []


class _NovelEvaluator:
    """Stands in for the LLM evaluator: surfaces an extra finding in a category
    that has no covering skill."""

    def __init__(self) -> None:
        self._inner = RuleBasedEvaluator()

    def evaluate(self, result):
        verdict = self._inner.evaluate(result)
        if result.action.skill_id == "web.missing_security_headers":
            verdict.extra_findings.append({
                "title": "Open redirect via returnUrl",
                "category": "open-redirect",
                "severity": "medium",
                "confidence": "suspected",
                "source": "llm-evaluator",
            })
        return verdict


def test_loop_closes_novel_finding_becomes_reviewable_skill_proposal():
    # End-to-end: a novel (LLM-style) finding in an uncovered category must be
    # distilled into a pending_review skill proposal. This is the self-improvement
    # closure, proven without needing an API key.
    store = MemoryStore(":memory:")
    risk_engine = RiskEngine()
    guard = AuthorizationGuard(
        AuthorizationRegistry.load(REGISTRY), risk_engine,
        fingerprinter=StaticFingerprinter(ok=True),
    )
    orch = Orchestrator(
        store=store, guard=guard, risk_engine=risk_engine,
        skill_registry=SkillRegistry.with_defaults(), scorer=Scorer(store.conn),
        fetch=fake_juice_shop_fetch, evaluator=Evaluator(_NovelEvaluator()),
        rate_sleep=lambda _s: None,
    )

    report = orch.run_engagement("local-juice-shop", "assess")
    assert any(d["category"] == "open-redirect" for d in report.distilled)

    # Discriminating: only distillation writes a kind='skill' with source='distilled'
    # (the extra-finding path writes kind='finding'); so this row proves the loop closed.
    proposed = store.conn.execute(
        "SELECT status, source FROM semantic_items "
        "WHERE kind='skill' AND source='distilled' AND tags LIKE '%open-redirect%'"
    ).fetchone()
    assert proposed is not None
    assert proposed["status"] == "pending_review"
