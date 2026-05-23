"""Measurement harness: how good is the system right now, and is it improving?

Runs one engagement, compares the findings against a ground-truth list of known
issues, and reports the **rediscovery rate** (fraction of known issues the system
actually found) plus per-skill signal stats. Each run is written to
measurements/<ts>.json and appended to measurements/trend.tsv, so improvement
over time is visible — that is the whole point of a "self-improving" system.

Baselines must be deterministic to be comparable, so the LLM evaluator is OFF by
default (it surfaces variable extra findings); pass --use-llm to opt in.

    python -m src.measure              # offline, deterministic (faithful fixture)
    python -m src.measure --live       # real requests against the lab on :3001
    python -m src.measure --live --use-llm
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.orchestrator import build_orchestrator
from src.scoring import Scorer


def build_scorecard(report, groundtruth: dict, scorer: Scorer, mode: str) -> dict:
    """Pure scoring: compare an EngagementReport to ground truth. Unit-testable."""
    issues = groundtruth.get("issues", [])
    found_skills = {f["skill_id"] for f in report.findings}
    found_categories = {
        f.get("finding", {}).get("category") for f in report.findings
    }
    found, missed = [], []
    for issue in issues:
        covered = (
            issue.get("detected_by") in found_skills
            or issue.get("category") in found_categories
        )
        (found if covered else missed).append(issue["id"])

    per_skill = []
    for outcome in report.skill_outcomes:
        stats = scorer.stats(outcome["skill_id"])
        per_skill.append({
            "skill_id": outcome["skill_id"],
            "ran": outcome["ran"],
            "has_signal": outcome["has_signal"],
            "runs": stats.runs,
            "signal_ratio": round(stats.signal_ratio, 3),
        })

    total = len(issues)
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "authorization": report.authorization_id,
        "llm_active": report.llm_active,
        "n_skills": len(report.skill_outcomes),
        "n_findings": len(report.findings),
        "n_pending_review": sum(1 for f in report.findings if f.get("review") == "pending_review"),
        "rediscovery_rate": round(len(found) / total, 3) if total else 0.0,
        "found": found,
        "missed": missed,
        "per_skill": per_skill,
    }


def _write_outputs(scorecard: dict, out_dir: str) -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    stamp = scorecard["ts"].replace(":", "").replace("-", "")[:15]
    path = os.path.join(out_dir, f"{stamp}.json")
    Path(path).write_text(json.dumps(scorecard, indent=2, sort_keys=True))
    Path(os.path.join(out_dir, "latest.json")).write_text(json.dumps(scorecard, indent=2, sort_keys=True))

    trend = Path(os.path.join(out_dir, "trend.tsv"))
    if not trend.exists():
        trend.write_text("ts\tmode\tn_skills\trediscovery_rate\tn_findings\n")
    with trend.open("a") as fh:
        fh.write(f"{scorecard['ts']}\t{scorecard['mode']}\t{scorecard['n_skills']}\t"
                 f"{scorecard['rediscovery_rate']}\t{scorecard['n_findings']}\n")
    return path


def run_measurement(
    *,
    authorization: str = "local-juice-shop",
    goal: str = "assess",
    live: bool = False,
    use_llm: bool = False,
    groundtruth_path: str = "groundtruth/juice-shop.json",
    out_dir: str = "measurements",
) -> dict:
    groundtruth = json.loads(Path(groundtruth_path).read_text())
    orch = build_orchestrator(dry_run=not live, llm=use_llm)
    report = orch.run_engagement(authorization, goal)
    scorecard = build_scorecard(report, groundtruth, orch.scorer, "live" if live else "offline")
    scorecard["scorecard_path"] = _write_outputs(scorecard, out_dir)
    return scorecard


def _print(card: dict) -> None:
    print(f"=== measurement ({card['mode']}) ===")
    print(f"authorization : {card['authorization']}")
    print(f"brains        : {'Claude (LLM)' if card['llm_active'] else 'deterministic'}")
    print(f"skills        : {card['n_skills']}")
    print(f"findings      : {card['n_findings']}  (pending review: {card['n_pending_review']})")
    rate_pct = card["rediscovery_rate"] * 100
    print(f"REDISCOVERY   : {rate_pct:.0f}%  ({len(card['found'])}/{len(card['found']) + len(card['missed'])} known issues)")
    if card["missed"]:
        print(f"  missed      : {', '.join(card['missed'])}  <- coverage gaps to close next")
    print("  note        : rediscovery measures known issues found, not unknown ones; "
          "it is only as good as groundtruth/*.json")
    print("per-skill:")
    for s in card["per_skill"]:
        flag = "signal" if s["has_signal"] else ("ran" if s["ran"] else "blocked")
        print(f"  - {s['skill_id']:<32} {flag:<7} runs={s['runs']} signal_ratio={s['signal_ratio']}")
    print(f"scorecard     : {card.get('scorecard_path')}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Measure rediscovery rate against ground truth.")
    parser.add_argument("--authorization", default="local-juice-shop")
    parser.add_argument("--goal", default="assess")
    parser.add_argument("--live", action="store_true", help="make real requests (needs the lab running)")
    parser.add_argument("--use-llm", action="store_true", help="enable the Claude evaluator (non-deterministic)")
    parser.add_argument("--groundtruth", default="groundtruth/juice-shop.json")
    parser.add_argument("--out", default="measurements")
    args = parser.parse_args(argv)

    card = run_measurement(
        authorization=args.authorization, goal=args.goal, live=args.live,
        use_llm=args.use_llm, groundtruth_path=args.groundtruth, out_dir=args.out,
    )
    _print(card)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
