from src.skills.web.info_disclosure_headers import InfoDisclosureHeaders
from src.tools.http_client import HttpResponse


def test_detects_leaky_custom_header():
    obs = InfoDisclosureHeaders().detect(
        HttpResponse(200, {"X-Recruiting": "/#/jobs"}, "http://localhost:3001")
    )
    leaked = {h["header"] for h in obs["leaked_headers"]}
    assert "x-recruiting" in leaked


def test_server_without_version_is_ignored_but_with_version_is_flagged():
    skill = InfoDisclosureHeaders()
    plain = skill.detect(HttpResponse(200, {"Server": "nginx"}, "http://x"))
    assert all(h["header"] != "server" for h in plain["leaked_headers"])

    versioned = skill.detect(HttpResponse(200, {"Server": "Apache/2.4.1"}, "http://x"))
    assert any(h["header"] == "server" for h in versioned["leaked_headers"])


def test_clean_headers_produce_no_finding():
    obs = InfoDisclosureHeaders().detect(
        HttpResponse(200, {"Content-Type": "text/html"}, "http://x")
    )
    assert obs["leaked_headers"] == []


def test_custom_watch_list_is_honored():
    skill = InfoDisclosureHeaders(watch=[{"header": "x-debug", "why": "debug leak"}])
    obs = skill.detect(HttpResponse(200, {"X-Debug": "on"}, "http://x"))
    assert obs["leaked_headers"][0]["header"] == "x-debug"
