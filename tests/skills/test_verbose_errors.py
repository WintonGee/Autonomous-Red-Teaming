from src.skills.web.verbose_errors import VerboseErrors
from src.tools.http_client import HttpResponse


def test_detects_stack_frame_and_error_class():
    body = ("UnauthorizedError: No Authorization header was found\n"
            "    at /juice-shop/build/routes/verify.js:0:0")
    sigs = VerboseErrors().detect(HttpResponse(401, {}, "http://x", body=body))
    assert "stack_frame" in sigs
    assert "error_class" in sigs


def test_benign_body_has_no_signatures():
    sigs = VerboseErrors().detect(
        HttpResponse(200, {}, "http://x", body="<!DOCTYPE html><title>OWASP Juice Shop</title>")
    )
    assert sigs == []


def test_run_reports_finding_for_verbose_probe():
    body = "SequelizeDatabaseError: bad\n    at db.js:12"

    class _Http:
        def get(self, url):
            return HttpResponse(500, {}, url, body=body)

    skill = VerboseErrors(probes=[{"path": "/boom", "why": "test"}])
    obs = skill.run(_Http(), "http://localhost:3001")
    assert obs["finding"]["category"] == "error-handling"
    assert obs["verbose_errors"][0]["path"] == "/boom"
