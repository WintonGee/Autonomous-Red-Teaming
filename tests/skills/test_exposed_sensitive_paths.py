from src.skills.web.exposed_sensitive_paths import ExposedSensitivePaths
from src.tools.http_client import HttpClient, HttpResponse


def _juice_fake(url, timeout=8.0):
    # Encodes Juice Shop's known structure: a few sensitive paths exist, others 404.
    pages = {
        "/ftp/acquisitions.md": (200, "# Planned Acquisitions\nThis document is confidential!"),
        "/ftp": (200, "Index of /ftp"),
        "/metrics": (200, "# HELP nodejs_version_info"),
    }
    for path, (code, body) in pages.items():
        if url.endswith(path):
            return HttpResponse(code, {}, url, body)
    return HttpResponse(404, {}, url, "not found")


def _client():
    return HttpClient(allowed_urls={"http://localhost:3001"}, fetch=_juice_fake)


def test_detects_only_actually_exposed_paths():
    probes = [
        {"path": "/ftp/acquisitions.md", "why": "confidential doc", "expect_contains": "confidential"},
        {"path": "/ftp", "why": "browsable folder", "expect_contains": "Index of"},
        {"path": "/metrics", "why": "metrics exposed", "expect_contains": "# HELP"},
        {"path": "/does-not-exist", "why": "should 404", "expect_contains": "x"},
    ]
    obs = ExposedSensitivePaths(probes=probes).run(_client(), "http://localhost:3001")
    exposed_paths = {e["path"] for e in obs["exposed"]}
    assert exposed_paths == {"/ftp/acquisitions.md", "/ftp", "/metrics"}
    assert obs["finding"]["category"] == "broken-access-control"
    assert obs["finding"]["evidence"]["exposed"]


def test_bare_200_without_marker_is_not_reported():
    # Evidence over claims: an SPA returns 200 for unknown paths; a probe with no
    # content marker must NOT be reported as exposed (regression for SPA fallback).
    probes = [{"path": "/metrics", "why": "no marker given"}]
    obs = ExposedSensitivePaths(probes=probes).run(_client(), "http://localhost:3001")
    assert obs["exposed"] == []
    assert "finding" not in obs


def test_content_marker_must_match():
    # 200 but missing the expected confidential marker -> not flagged.
    probes = [{"path": "/ftp/acquisitions.md", "why": "x", "expect_contains": "NOT-PRESENT"}]
    obs = ExposedSensitivePaths(probes=probes).run(_client(), "http://localhost:3001")
    assert obs["exposed"] == []
    assert "finding" not in obs


def test_ships_with_a_real_probe_list():
    skill = ExposedSensitivePaths()  # loads exposed_sensitive_paths.json
    assert skill.to_record()["probe_count"] >= 1
