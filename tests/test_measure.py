import json
from pathlib import Path

from src.measure import build_scorecard, run_measurement
from src.orchestrator import build_orchestrator

GROUNDTRUTH = "groundtruth/juice-shop.json"


def test_offline_finds_every_covered_issue_and_flags_the_gap():
    # Every ground-truth issue that has a built skill must be rediscovered; the
    # intentional coverage gap (an issue whose detector does not exist yet) must be
    # reported as missed, keeping the rate honestly below 100%.
    groundtruth = json.loads(Path(GROUNDTRUTH).read_text())
    orch = build_orchestrator(dry_run=True, llm=False)
    report = orch.run_engagement("local-juice-shop", "assess")
    card = build_scorecard(report, groundtruth, orch.scorer, "offline")

    assert "js-robots-disclosure" in card["missed"]   # the deliberate gap
    covered = {i["id"] for i in groundtruth["issues"] if i["id"] != "js-robots-disclosure"}
    assert set(card["found"]) == covered
    assert 0 < card["rediscovery_rate"] < 1.0


def test_missing_skill_lowers_rediscovery():
    # Removing a skill must lower the rediscovery rate — proving the metric tracks
    # capability, not just "ran without error".
    groundtruth = json.loads(Path(GROUNDTRUTH).read_text())
    full = build_orchestrator(dry_run=True, llm=False)
    full_card = build_scorecard(
        full.run_engagement("local-juice-shop", "assess"), groundtruth, full.scorer, "offline")

    reduced = build_orchestrator(dry_run=True, llm=False)
    reduced.skills._skills.pop("web.cors_misconfiguration")
    reduced_card = build_scorecard(
        reduced.run_engagement("local-juice-shop", "assess"), groundtruth, reduced.scorer, "offline")

    assert reduced_card["rediscovery_rate"] < full_card["rediscovery_rate"]
    assert "js-cors-wildcard" in reduced_card["missed"]


def test_run_measurement_writes_scorecard(tmp_path):
    card = run_measurement(live=False, out_dir=str(tmp_path))
    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "trend.tsv").exists()
    assert card["scorecard_path"].endswith(".json")
