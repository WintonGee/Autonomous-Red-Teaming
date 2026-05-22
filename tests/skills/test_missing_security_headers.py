from src.skills.web.missing_security_headers import REQUIRED_HEADERS, MissingSecurityHeaders
from src.tools.http_client import HttpResponse


def test_detects_missing_headers():
    obs = MissingSecurityHeaders().detect(
        HttpResponse(200, {"X-Content-Type-Options": "nosniff"}, "http://localhost:3000")
    )
    assert "content-security-policy" in obs["missing_headers"]
    assert "x-content-type-options" not in obs["missing_headers"]  # present (case-insensitive)
    assert obs["status_code"] == 200


def test_no_missing_when_all_present():
    headers = {h: "value" for h in REQUIRED_HEADERS}
    obs = MissingSecurityHeaders().detect(HttpResponse(200, headers, "http://localhost:3000"))
    assert obs["missing_headers"] == []
