import json
from pathlib import Path

from src.authorization import AuthorizationGuard, AuthorizationRegistry, StaticFingerprinter
from src.measure import build_scorecard
from src.memory.store import MemoryStore
from src.orchestrator import Orchestrator
from src.risk import RiskEngine
from src.scoring import Scorer
from src.skills.registry import SkillRegistry
from src.tools.http_client import fake_juice_shop_fetch

REGISTRY = "authorizations/authorized-targets.json"
GROUNDTRUTH = "groundtruth/juice-shop.json"


def _orch(generated_dir):
    store = MemoryStore(":memory:")
    risk_engine = RiskEngine()
    guard = AuthorizationGuard(AuthorizationRegistry.load(REGISTRY), risk_engine,
                               fingerprinter=StaticFingerprinter(ok=True))
    return Orchestrator(
        store=store, guard=guard, risk_engine=risk_engine,
        skill_registry=SkillRegistry.with_defaults(), scorer=Scorer(store.conn),
        fetch=fake_juice_shop_fetch, generated_dir=str(generated_dir), rate_sleep=lambda _s: None,
    )


def test_autonomous_understands_runs_and_creates_a_new_skill(tmp_path):
    orch = _orch(tmp_path)
    report = orch.run_autonomous("local-juice-shop", "find vulnerabilities")

    # 1. It built an understanding and found the robots gap.
    assert "OWASP Juice Shop" in report.tech
    assert any(g["category"] == "crawler-policy-disclosure" for g in report.planned_gaps)

    # 2. It tried the existing arsenal.
    assert len(report.skill_outcomes) >= 5
    assert all(o["ran"] for o in report.skill_outcomes)

    # 3. It CREATED a new skill for the gap, ran it, and got signal.
    created = [g for g in report.generated_skills if g["category"] == "crawler-policy-disclosure"]
    assert created and created[0]["ran"] and created[0]["has_signal"]

    # 4. The generated skill was persisted (library grew) and is pending_review.
    assert list(Path(tmp_path).glob("*.json"))
    proposed = orch.store.conn.execute(
        "SELECT status, source FROM semantic_items WHERE kind='skill' AND tags LIKE '%crawler-policy-disclosure%'"
    ).fetchone()
    assert proposed["status"] == "pending_review"


def test_autonomous_closes_the_coverage_gap(tmp_path):
    orch = _orch(tmp_path)
    report = orch.run_autonomous("local-juice-shop", "find vulnerabilities")
    card = build_scorecard(report, json.loads(Path(GROUNDTRUTH).read_text()), orch.scorer, "offline")
    # The trusted skills cover 5/6; the autonomously-generated robots skill closes
    # the known gap -> 6/6. (Honest framing: it closes a KNOWN gap; the LLM
    # generator generalizes this beyond gaps the heuristic recognizes.)
    assert "js-robots-disclosure" in card["found"]
    assert card["rediscovery_rate"] == 1.0


def test_generated_skill_rejoins_arsenal_next_run_and_is_not_regenerated(tmp_path):
    _orch(tmp_path).run_autonomous("local-juice-shop", "g")        # run 1: generates robots skill
    report2 = _orch(tmp_path).run_autonomous("local-juice-shop", "g")  # run 2: should reuse, not recreate

    # The robots skill now runs as part of the existing arsenal...
    assert any(o["skill_id"].startswith("web.generated.crawler_policy") for o in report2.skill_outcomes)
    # ...and is NOT generated again (dedupe across runs).
    assert not any(g["category"] == "crawler-policy-disclosure" for g in report2.generated_skills)
