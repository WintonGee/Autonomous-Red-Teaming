"""Orchestrator: runs learning cycles / engagements and enforces the safety gates.

Two entrypoints:
  run_cycle      - one planned skill, scored (the learning-loop demo).
  run_engagement - run every eligible skill through the gates in one engagement,
                   collect deduped findings + evidence (a real assessment).

Every stage writes to memory. Authorization includes fingerprint identity
verification (fail closed). Agent brains are deterministic by default; wiring an
LLM means swapping a reasoner (see src/README.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
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
from src.agents.reasoners import RuleBasedEvaluator, RuleBasedLearner, RuleBasedPlanner
from src.authorization import (
    AuthorizationError,
    AuthorizationGuard,
    AuthorizationRegistry,
    HttpFingerprinter,
    StaticFingerprinter,
)
from src.memory.dedup import content_hash
from src.memory.distill import distill_engagement
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


@dataclass
class EngagementReport:
    authorization_id: str
    goal: str
    engagement_id: str
    identity_ok: bool = False
    llm_active: bool = False
    findings: list = field(default_factory=list)
    skill_outcomes: list = field(default_factory=list)
    evidence_dir: Optional[str] = None
    context_blocks: list = field(default_factory=list)
    distilled: list = field(default_factory=list)  # skills proposed by end-of-engagement distillation


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
        evidence_dir: Optional[str] = None,
        rate_sleep: Optional[Callable[[float], None]] = None,
        llm_client=None,
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
        self.evidence_dir = evidence_dir
        self.llm_client = llm_client  # set when LLM brains are active; None otherwise
        # Rate-limiter sleep: real for live runs, no-op offline (nothing to be polite to).
        self.rate_sleep = rate_sleep or time.sleep
        self.skills.seed_semantic(store)  # idempotent

    def _drain_llm_audit(self, engagement_id: str, authorization_id: str) -> None:
        """Persist a durable record of each external LLM call (no raw payload)."""
        if self.llm_client is None:
            return
        for record in self.llm_client.drain_audit():
            self.store.add_event(
                engagement_id=engagement_id, authorization_id=authorization_id,
                event_type="llm_call", content=json.dumps(record, sort_keys=True),
                salience="salient",
            )

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

    def _store_evidence(self, engagement_id: str, authorization_id: str, skill_id: str, finding: dict) -> Optional[int]:
        if not self.evidence_dir:
            return None
        target_dir = os.path.join(self.evidence_dir, engagement_id)
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, f"{skill_id}.json")
        payload = json.dumps(finding, indent=2, sort_keys=True)
        Path(path).write_text(payload)
        sha = hashlib.sha256(payload.encode()).hexdigest()
        return self.store.add_evidence_ref(
            engagement_id=engagement_id, authorization_id=authorization_id,
            path=path, sha256=sha, media_type="application/json", size_bytes=len(payload),
        )

    def _persist_finding(self, engagement_id: str, auth_id: str, skill_id: str, finding: dict) -> tuple[bool, Optional[int]]:
        """Write a finding if not a duplicate. Returns (is_new, evidence_ref)."""
        fh = content_hash(json.dumps(finding, sort_keys=True))
        exists = self.store.conn.execute(
            "SELECT 1 FROM semantic_items WHERE kind='finding' AND content_hash=? AND authorization_id=?",
            (fh, auth_id),
        ).fetchone()
        if exists:
            return False, None
        evidence_ref = self._store_evidence(engagement_id, auth_id, skill_id, finding)
        self.store.add_semantic_item(
            kind="finding", title=finding["title"], authorization_id=auth_id,
            content=finding, tags=[finding.get("category", "unknown")],
        )
        return True, evidence_ref

    def _log_finding_event(self, engagement_id: str, auth_id: str, finding: dict) -> None:
        """Persist a structured finding into the episodic log so end-of-engagement
        distillation has material to reason over."""
        self.store.add_event(
            engagement_id=engagement_id, authorization_id=auth_id,
            event_type="finding", content=json.dumps(finding, sort_keys=True),
            salience="salient",
        )

    def _persist_extra_finding(self, auth_id: str, finding: dict) -> bool:
        """Persist an LLM-discovered finding as pending_review (deduped). Returns is_new."""
        fh = content_hash(json.dumps(finding, sort_keys=True))
        exists = self.store.conn.execute(
            "SELECT 1 FROM semantic_items WHERE kind='finding' AND content_hash=? AND authorization_id=?",
            (fh, auth_id),
        ).fetchone()
        if exists:
            return False
        self.store.add_semantic_item(
            kind="finding", title=finding["title"], authorization_id=auth_id,
            content=finding, tags=[finding.get("category", "unknown")],
            source=finding.get("source", "llm-evaluator"), status="pending_review",
        )
        return True

    # --------------------------------------------------------------- engagement
    def run_engagement(self, authorization_id: str, goal: str, today: Optional[date] = None) -> EngagementReport:
        engagement_id = uuid.uuid4().hex[:12]

        # Authorize + fingerprint-verify the target (fail closed).
        auth = self.guard.authorize_target(authorization_id, today)
        max_risk = self.risk_engine.max_allowed(auth.risk_limit)
        wm = start_engagement(
            self.store, authorization_id=auth.id,
            authorization_facts={"scope": auth.target, "risk_limit": auth.risk_limit, "max_risk": max_risk},
            goal=goal,
        )
        report = EngagementReport(authorization_id=auth.id, goal=goal, engagement_id=engagement_id,
                                  identity_ok=True, evidence_dir=self.evidence_dir,
                                  llm_active=self.llm_client is not None)
        try:
            rate = RateLimiter(auth.rate_limit.get("max_requests_per_second", 1), sleep=self.rate_sleep)
            http = HttpClient(allowed_urls={auth.target}, fetch=self.fetch, rate_limiter=rate)
            executor = Executor(http, self.skills)

            infos = self._skill_infos()
            infos.sort(key=lambda s: (-s.signal_ratio, s.runs, s.skill_id))  # planner priority
            verdicts: list[Verdict] = []
            for info in infos:
                outcome = {"skill_id": info.skill_id, "ran": False, "has_signal": False, "blocked_reason": None}
                action = ProposedAction(skill_id=info.skill_id, target_url=auth.target,
                                        action_type=info.action_type, risk_level=info.risk_level,
                                        rationale=f"engagement skill {info.skill_id}")
                # Gate every action (fail closed).
                try:
                    self.guard.authorize_action(auth, action.action_type, action.risk_level)
                except AuthorizationError as exc:
                    outcome["blocked_reason"] = str(exc)
                    self.store.add_event(engagement_id=engagement_id, authorization_id=auth.id,
                                         event_type="decision", content=f"BLOCKED {info.skill_id}: {exc}",
                                         salience="salient")
                    report.skill_outcomes.append(outcome)
                    continue

                result = executor.execute(action)
                outcome["ran"] = True
                self.store.add_event(engagement_id=engagement_id, authorization_id=auth.id,
                                     event_type="tool_output", content=json.dumps(result.observations)[:500],
                                     salience="ephemeral")

                verdict = self.evaluator.evaluate(result)
                verdicts.append(verdict)
                outcome["has_signal"] = verdict.has_signal
                wm.add(f"{info.skill_id}: {verdict.rationale}", salience="salient")
                self.store.add_event(engagement_id=engagement_id, authorization_id=auth.id,
                                     event_type="evaluation", content=f"{info.skill_id}: {verdict.rationale}",
                                     salience="salient")

                if verdict.finding:
                    is_new, evidence_ref = self._persist_finding(engagement_id, auth.id, info.skill_id, verdict.finding)
                    report.findings.append({
                        "skill_id": info.skill_id, "title": verdict.finding["title"],
                        "severity": verdict.finding.get("severity"), "new": is_new,
                        "evidence_ref": evidence_ref, "source": "skill", "finding": verdict.finding,
                    })
                    self._log_finding_event(engagement_id, auth.id, verdict.finding)

                # LLM-discovered findings are persisted as pending_review, never auto-trusted.
                for extra in verdict.extra_findings:
                    is_new = self._persist_extra_finding(auth.id, extra)
                    report.findings.append({
                        "skill_id": info.skill_id, "title": extra["title"],
                        "severity": extra.get("severity"), "new": is_new,
                        "source": extra.get("source", "llm-evaluator"),
                        "review": "pending_review", "finding": extra,
                    })
                    self._log_finding_event(engagement_id, auth.id, extra)

                self.scorer.record(skill_id=info.skill_id, authorization_id=auth.id,
                                   had_signal=verdict.has_signal, finding_confirmed=bool(verdict.finding),
                                   error=verdict.failure_reason)
                report.skill_outcomes.append(outcome)

            # Learn across the engagement's verdicts -> reviewed skill proposals.
            for proposal in self.learner.learn(verdicts, infos):
                self.store.add_semantic_item(
                    kind="skill", title=proposal.title, content=proposal.payload,
                    tags=[proposal.category], source="llm-learner", status="pending_review",
                )

            # Distill the episodic record into reusable skill proposals for any
            # finding-category still uncovered (deduped against all known skills,
            # including the Learner's just-added proposals). Human review required.
            for prop in distill_engagement(self.store, engagement_id):
                self.store.add_semantic_item(
                    kind="skill", title=prop["title"], content=prop["payload"],
                    tags=[prop["category"]], source=prop["source"], status="pending_review",
                )
                report.distilled.append({"title": prop["title"], "category": prop["category"]})

            self._drain_llm_audit(engagement_id, auth.id)
            report.context_blocks = wm.render()
            return report
        finally:
            run_gc(self.store)

    # -------------------------------------------------------------------- cycle
    def run_cycle(self, authorization_id: str, goal: str, today: Optional[date] = None) -> CycleReport:
        engagement_id = uuid.uuid4().hex[:12]

        # 1. Authorize + fingerprint-verify the target (fail closed).
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
            rate = RateLimiter(auth.rate_limit.get("max_requests_per_second", 1), sleep=self.rate_sleep)
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
                is_new, _ = self._persist_finding(engagement_id, auth.id, action.skill_id, verdict.finding)
                report.finding_written = is_new

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

            self._drain_llm_audit(engagement_id, auth.id)
            report.context_blocks = wm.render()
            return report
        finally:
            run_gc(self.store)


def build_orchestrator(
    *,
    store: Optional[MemoryStore] = None,
    registry_path: str = "authorizations/authorized-targets.json",
    dry_run: bool = True,
    evidence_dir: Optional[str] = None,
    llm: bool = True,
    llm_client=None,
) -> Orchestrator:
    store = store or MemoryStore(":memory:")
    risk_engine = RiskEngine(project_ceiling=1)
    if dry_run:
        fingerprinter = StaticFingerprinter(ok=True)
        fetch = fake_juice_shop_fetch
        evidence_dir = None  # offline runs don't write evidence files
    else:
        fingerprinter = HttpFingerprinter()
        fetch = urllib_fetch
        evidence_dir = evidence_dir or "evidence"
    guard = AuthorizationGuard(AuthorizationRegistry.load(registry_path), risk_engine, fingerprinter=fingerprinter)

    # LLM brains activate only when a client is available (ANTHROPIC_API_KEY set);
    # otherwise the deterministic reasoners are used. The LLM proposes; code gates.
    planner = evaluator = learner = None
    active_client = None
    if llm:
        from src.agents.llm import ClaudeClient, ClaudeEvaluator, ClaudeLearner, ClaudePlanner
        client = llm_client if llm_client is not None else ClaudeClient()
        if client.available():
            active_client = client
            planner = Planner(ClaudePlanner(client, RuleBasedPlanner()))
            evaluator = Evaluator(ClaudeEvaluator(client, RuleBasedEvaluator()))
            learner = Learner(ClaudeLearner(client, RuleBasedLearner()))

    return Orchestrator(
        store=store, guard=guard, risk_engine=risk_engine,
        skill_registry=SkillRegistry.with_defaults(), scorer=Scorer(store.conn),
        fetch=fetch, evidence_dir=evidence_dir,
        planner=planner, evaluator=evaluator, learner=learner, llm_client=active_client,
        rate_sleep=(None if not dry_run else (lambda _seconds: None)),  # offline: don't actually sleep
    )


def _print_cycle(report: CycleReport) -> None:
    print(f"engagement   : {report.engagement_id}")
    print(f"authorization: {report.authorization_id}")
    print(f"goal         : {report.goal}")
    if report.blocked_reason:
        print(f"BLOCKED      : {report.blocked_reason}")
    if report.action:
        print(f"plan         : {report.action.skill_id} -> {report.action.target_url}")
    if report.verdict:
        print(f"verdict      : signal={report.verdict.has_signal} :: {report.verdict.rationale}")


def _print_engagement(r: EngagementReport) -> None:
    print(f"engagement   : {r.engagement_id}")
    print(f"authorization: {r.authorization_id}")
    print(f"identity     : {'VERIFIED' if r.identity_ok else 'UNVERIFIED'}")
    print(f"brains       : {'Claude (LLM)' if r.llm_active else 'deterministic (set ANTHROPIC_API_KEY for LLM)'}")
    print(f"goal         : {r.goal}")
    print("skills:")
    for o in r.skill_outcomes:
        status = "ran" if o["ran"] else f"BLOCKED ({o['blocked_reason']})"
        print(f"  - {o['skill_id']}: {status}, signal={o['has_signal']}")
    print(f"findings ({len(r.findings)}):")
    for f in r.findings:
        tag = f.get("review", f.get("source", "skill"))
        print(f"  - [{f['severity']}] {f['title']}  ({tag})")
        print(f"      skill={f['skill_id']} new={f['new']}")
    if r.evidence_dir:
        print(f"evidence     : {r.evidence_dir}/{r.engagement_id}/")
    print("--- working memory (rendered context) ---")
    for b in r.context_blocks:
        text = b["text"].replace("\n", " | ")
        print(f"  [{b['region']:<7}] cacheable={b['cacheable']} :: {text}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run an autonomous red-teaming engagement or cycle.")
    parser.add_argument("--authorization", default="local-juice-shop")
    parser.add_argument("--goal", default="assess")
    parser.add_argument("--mode", choices=["engagement", "cycle"], default="engagement")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="use the offline fake HTTP client (default)")
    parser.add_argument("--live", dest="dry_run", action="store_false",
                        help="make real requests (requires the target to be running)")
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args(argv)

    orch = build_orchestrator(dry_run=args.dry_run)
    if args.mode == "engagement":
        _print_engagement(orch.run_engagement(args.authorization, args.goal))
    else:
        for i in range(args.cycles):
            if args.cycles > 1:
                print(f"\n===== cycle {i + 1}/{args.cycles} =====")
            _print_cycle(orch.run_cycle(args.authorization, args.goal))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
