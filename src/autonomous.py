"""Point-and-go autonomous assessment.

    python -m src.autonomous --live                  # against the lab on :3001
    python -m src.autonomous                          # offline (faithful fixture)
    python -m src.autonomous --live --use-llm         # LLM recon + skill generation

Flow: understand the target → try the existing skill arsenal → create, dedupe,
and run new skills for the gaps → score against ground truth. Generated skills
persist under skills/_generated/ and rejoin the arsenal next run (the library
grows). Findings from generated skills are pending_review; the trusted library is
never auto-modified.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from src.measure import _write_outputs, build_scorecard
from src.orchestrator import build_orchestrator


def _print(report, scorecard: Optional[dict], live: bool) -> None:
    print(f"=== autonomous assessment ({'live' if live else 'offline'}) ===")
    print(f"authorization : {report.authorization_id}")
    print(f"identity      : {'VERIFIED' if report.identity_ok else 'UNVERIFIED'}")
    print(f"brains        : {'Claude (LLM)' if report.llm_active else 'deterministic'}")
    print(f"understanding : {report.profile_summary}")
    if report.tech:
        print(f"tech          : {', '.join(report.tech)}")
    if report.planned_gaps:
        print(f"gaps found    : {', '.join(g.get('category', '?') for g in report.planned_gaps)}")
    if report.surface:
        s = report.surface
        params = s.get("params", [])
        print(f"surface       : {s.get('pages', 0)} pages, {s.get('forms', 0)} forms, "
              f"{s.get('endpoints', 0)} endpoints, {len(params)} parameters"
              + (f" ({', '.join(params[:8])}{'…' if len(params) > 8 else ''})" if params else ""))
        for note in s.get("notes", []):
            print(f"                ! {note}")

    print(f"\nexisting arsenal ({len(report.skill_outcomes)} skills tried):")
    for o in report.skill_outcomes:
        status = "signal" if o["has_signal"] else ("ran" if o["ran"] else f"BLOCKED ({o['blocked_reason']})")
        print(f"  - {o['skill_id']:<34} {status}")

    if report.generation_audit:
        a = report.generation_audit
        print(f"\ngeneration    : proposed {a.get('proposed', 0)}, "
              f"rejected-unsafe {a.get('rejected_unsafe', 0)}, "
              f"dropped-duplicate {a.get('dropped_duplicate', 0)}, "
              f"dropped-semantic {a.get('dropped_semantic', 0)}, created {a.get('created', 0)}")
    print(f"\nskills CREATED this run ({len(report.generated_skills)}):")
    for g in report.generated_skills:
        status = "signal" if g["has_signal"] else ("ran" if g["ran"] else f"BLOCKED ({g['blocked_reason']})")
        print(f"  - {g['skill_id']:<34} [{g['source']}] {status}")
    if not report.generated_skills:
        print("  (none — no uncovered gaps, or generator proposed only duplicates)")

    print(f"\nfindings ({len(report.findings)}):")
    for f in report.findings:
        tag = f.get("review", f.get("source", "skill"))
        print(f"  - [{f['severity']}] {f['title']}  ({tag})")

    if scorecard:
        rate = scorecard["rediscovery_rate"] * 100
        print(f"\nREDISCOVERY   : {rate:.0f}%  ({len(scorecard['found'])}/"
              f"{len(scorecard['found']) + len(scorecard['missed'])} known issues)")
        if scorecard["missed"]:
            print(f"  still missed : {', '.join(scorecard['missed'])}")
        print(f"  note        : rediscovery measures known issues found; it is only as good as groundtruth/*.json")
        print(f"scorecard     : {scorecard.get('scorecard_path')}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a fully autonomous assessment.")
    parser.add_argument("--authorization", default="local-juice-shop")
    parser.add_argument("--goal", default="find vulnerabilities")
    parser.add_argument("--live", action="store_true", help="make real requests (needs the lab running)")
    parser.add_argument("--use-llm", action="store_true", help="LLM recon + skill generation (needs ANTHROPIC_API_KEY)")
    parser.add_argument("--groundtruth", default="groundtruth/juice-shop.json")
    parser.add_argument("--out", default="measurements")
    args = parser.parse_args(argv)

    orch = build_orchestrator(dry_run=not args.live, llm=args.use_llm)
    report = orch.run_autonomous(args.authorization, args.goal)

    scorecard = None
    gt_path = Path(args.groundtruth)
    if gt_path.exists():
        scorecard = build_scorecard(report, json.loads(gt_path.read_text()), orch.scorer,
                                    "live" if args.live else "offline")
        scorecard["mode"] = "autonomous-" + scorecard["mode"]
        scorecard["scorecard_path"] = _write_outputs(scorecard, args.out)
    _print(report, scorecard, args.live)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
