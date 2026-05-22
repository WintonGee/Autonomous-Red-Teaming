"""Orchestrator: runs one full learning cycle and enforces the safety gates.

Cycle: authorize target -> fresh working memory -> plan -> gate action ->
execute (scoped tool) -> evaluate -> persist finding (deduped) -> learn ->
score. Every stage writes to memory; the cycle returns a report including the
rendered working-memory blocks.

The agents' brains are deterministic by default (offline, testable). Wiring an
LLM means swapping a reasoner — start with the Learner (see src/README.md).
"""
from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from src.agents import (
    EngagementState,
    Evaluator,
    Executor,
    Learner,
    Planner,
    ProposedAction,
    SkillInfo,
    Verdict,
)
from src.authorization import AuthorizationError, AuthorizationGuard, AuthorizationRegistry
from src.memory.dedup import content_hash
from src.memory.gc import run_gc
from src.memory.session import start_engagement
from src.memory.store import MemoryStore
from src.risk import RiskEngine
from src.scoring import Scorer
from src.skills.registry import SkillRegistry
from src.tools.http_client import Fetch, HttpClient, RateLimiter, fake_juice_shop_fetch, urllib_fetch


@dataclass
class CycleReport:
    authorization_id: str
    goal: str
    engagement_id: str
    action: Optional[ProposedAction] = None
    verdict: Optional[Verdict] = None
    proposals: list = field(default_factory=list)
    finding_written: bool = False
    blocked_reason: Optional[str] = None
    context_blocks: list = field(default_factory=list)


class Orchestrator:
    def __init__(
        self,
        store: MemoryStore,
        guard: AuthorizationGuard,
        risk_engine: RiskEngine,
        skill_registry: SkillRegistry,
        scorer: Scorer,
        fetch: Fetch,
        planner: Optional[Planner] = None,
        evaluator: Optional[Evaluator] = None,
        learner: Optional[Learner] = None,
    ) -> None:
        self.store = store
        self.guard = guard
        self.risk_engine = risk_engine
        self.skills = skill_registry
        self.scorer = scorer
        self.fetch = fetch
        self.planner = planner or Planner()
        self.evaluator = evaluator or Evaluator()
        self.learner = learner or Learner()
        self.skills.seed_semantic(store)  # idempotent

    def _skill_infos(self) -> list[SkillInfo]:
        infos = []
        for skill in self.skills.all():
            stats = self.scorer.stats(skill.id)
            infos.append(
                SkillInfo(
                    skill_id=skill.id,
                    name=skill.name,
                    category=skill.category,
                    risk_level=skill.risk_level,
                    action_type=skill.action_type,
                    runs=stats.runs,
                    signal_ratio=stats.signal_ratio,
                )
            )
        return infos

    def run_cycle(self, authorization_id: str, goal: str, today: Optional[date] = None) -> CycleReport:
        engagement_id = uuid.uuid4().hex[:12]

        # 1. Authorize the target (fail closed). No memory exists yet if this raises.
        auth = self.guard.authorize_target(authorization_id, today)

        # 2. Fresh working memory seeded with pinned safety facts.
        max_risk = self.risk_engine.max_allowed(auth.risk_limit)
        wm = start_engagement(
            self.store,
            authorization_id=auth.id,
            authorization_facts={"scope": auth.target, "risk_limit": auth.risk_limit, "max_risk": max_risk},
            goal=goal,
        )
        report = CycleReport(authorization_id=auth.id, goal=goal, engagement_id=engagement_id)

        # GC sweep runs after every cycle (success or early return): evict expired
        # ephemeral events and collapse exact duplicates so the log stays bounded.
        try:
            # 3. Plan from scoped skills + their accumulated metrics.
            state = EngagementState(
                authorization_id=auth.id,
                goal=goal,
                target_url=auth.target,
                available_skills=self._skill_infos(),
                max_risk=max_risk,
            )
            action = self.planner.plan(state)
            if action is None:
                report.blocked_reason = "no eligible skill within risk ceiling"
                self.store.add_event(engagement_id=engagement_id, authorization_id=auth.id,
                                     event_type="decision", content=report.blocked_reason, salience="salient")
                report.context_blocks = wm.render()
                return report
            report.action = action
            wm.add(f"plan: {action.rationale}", salience="salient")
            self.store.add_event(engagement_id=engagement_id, authorization_id=auth.id,
                                 event_type="decision", content=action.rationale, salience="salient")

            # 4. Gate the proposed action (fail closed).
            try:
                self.guard.authorize_action(auth, action.action_type, action.risk_level)
            except AuthorizationError as exc:
                report.blocked_reason = str(exc)
                self.store.add_event(engagement_id=engagement_id, authorization_id=auth.id,
                                     event_type="decision", content=f"BLOCKED: {exc}", salience="salient")
                report.context_blocks = wm.render()
                return report

            # 5. Execute via a target-scoped tool (defense in depth in HttpClient).
            rate = RateLimiter(auth.rate_limit.get("max_requests_per_second", 1))
            http = HttpClient(allowed_urls={auth.target}, fetch=self.fetch, rate_limiter=rate)
            result = Executor(http, self.skills).execute(action)
            self.store.add_event(engagement_id=engagement_id, authorization_id=auth.id,
                                 event_type="tool_output", content=json.dumps(result.observations)[:500],
                                 salience="ephemeral")

            # 6. Evaluate.
            verdict = self.evaluator.evaluate(result)
            report.verdict = verdict
            wm.add(f"verdict: {verdict.rationale}", salience="salient")
            self.store.add_event(engagement_id=engagement_id, authorization_id=auth.id,
                                 event_type="evaluation", content=verdict.rationale, salience="salient")

            # 7. Persist the finding (deduped, authorization-scoped).
            if verdict.finding:
                fh = content_hash(json.dumps(verdict.finding, sort_keys=True))
                exists = self.store.conn.execute(
                    "SELECT 1 FROM semantic_items WHERE kind='finding' AND content_hash=? AND authorization_id=?",
                    (fh, auth.id),
                ).fetchone()
                if not exists:
                    self.store.add_semantic_item(kind="finding", title=verdict.finding["title"],
                                                 authorization_id=auth.id, content=verdict.finding,
                                                 tags=[verdict.finding.get("category", "unknown")])
                    report.finding_written = True

            # 8. Learn (reuse before create; LLM learner is the next milestone).
            proposals = self.learner.learn([verdict], state.available_skills)
            report.proposals = proposals
            for p in proposals:
                self.store.add_semantic_item(kind="skill", title=p.title, content=p.payload,
                                             tags=[p.category], source="distilled", status="pending_review")

            # 9. Score (persists across cycles -> drives future planning).
            self.scorer.record(skill_id=action.skill_id, authorization_id=auth.id,
                               had_signal=verdict.has_signal, finding_confirmed=bool(verdict.finding),
                               error=verdict.failure_reason)

            report.context_blocks = wm.render()
            return report
        finally:
            run_gc(self.store)


def build_orchestrator(
    *,
    store: Optional[MemoryStore] = None,
    registry_path: str = "authorizations/authorized-targets.json",
    dry_run: bool = True,
) -> Orchestrator:
    store = store or MemoryStore(":memory:")
    risk_engine = RiskEngine(project_ceiling=1)
    guard = AuthorizationGuard(AuthorizationRegistry.load(registry_path), risk_engine)
    fetch = fake_juice_shop_fetch if dry_run else urllib_fetch
    return Orchestrator(
        store=store, guard=guard, risk_engine=risk_engine,
        skill_registry=SkillRegistry.with_defaults(), scorer=Scorer(store.conn), fetch=fetch,
    )


def _print_report(report: CycleReport) -> None:
    print(f"engagement   : {report.engagement_id}")
    print(f"authorization: {report.authorization_id}")
    print(f"goal         : {report.goal}")
    if report.blocked_reason:
        print(f"BLOCKED      : {report.blocked_reason}")
    if report.action:
        print(f"plan         : {report.action.skill_id} -> {report.action.target_url}")
        print(f"               {report.action.rationale}")
    if report.verdict:
        print(f"verdict      : signal={report.verdict.has_signal} "
              f"confidence={report.verdict.confidence} :: {report.verdict.rationale}")
        if report.verdict.finding:
            print(f"finding      : {report.verdict.finding['title']} "
                  f"(new={report.finding_written})")
    print(f"proposals    : {[p.title for p in report.proposals] or 'none (reuse before create)'}")
    print("--- working memory (rendered context) ---")
    for block in report.context_blocks:
        text = block["text"].replace("\n", " | ")
        print(f"  [{block['region']:<7}] cacheable={block['cacheable']} :: {text}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run one autonomous red-teaming cycle.")
    parser.add_argument("--authorization", default="local-juice-shop")
    parser.add_argument("--goal", default="missing-headers")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="use the offline fake HTTP client (default)")
    parser.add_argument("--live", dest="dry_run", action="store_false",
                        help="make real requests (requires the target to be running)")
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args(argv)

    orch = build_orchestrator(dry_run=args.dry_run)
    for i in range(args.cycles):
        if args.cycles > 1:
            print(f"\n===== cycle {i + 1}/{args.cycles} =====")
        _print_report(orch.run_cycle(args.authorization, args.goal))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
