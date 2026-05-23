import json
from pathlib import Path

from src.measure import build_scorecard, run_measurement
from src.orchestrator import build_orchestrator

GROUNDTRUTH = "groundtruth/juice-shop.json"


def test_offline_rediscovers_all_known_issues():
    # The faithful offline fixture models every ground-truth issue, so a correct
    # system + correct skills must rediscover 100% deterministically.
    groundtruth = json.loads(Path(GROUNDTRUTH).read_text())
    orch = build_orchestrator(dry_run=True, llm=False)
    report = orch.run_engagement("local-juice-shop", "assess")
    card = build_scorecard(report, groundtruth, orch.scorer, "offline")

    assert card["rediscovery_rate"] == 1.0
    assert card["missed"] == []
    assert card["n_findings"] == len(groundtruth["issues"])


def test_missing_skill_lowers_rediscovery():
    # Removing a skill must show up as a lower rediscovery rate — proving the
    # metric actually tracks capability, not just "ran without error".
    groundtruth = json.loads(Path(GROUNDTRUTH).read_text())
    orch = build_orchestrator(dry_run=True, llm=False)
    orch.skills._skills.pop("web.cors_misconfiguration")
    report = orch.run_engagement("local-juice-shop", "assess")
    card = build_scorecard(report, groundtruth, orch.scorer, "offline")

    assert card["rediscovery_rate"] < 1.0
    assert "js-cors-wildcard" in card["missed"]


def test_run_measurement_writes_scorecard(tmp_path):
    card = run_measurement(live=False, out_dir=str(tmp_path))
    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "trend.tsv").exists()
    assert card["scorecard_path"].endswith(".json")
