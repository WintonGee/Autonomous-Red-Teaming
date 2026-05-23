from src.skills.web.cors_misconfiguration import CorsMisconfiguration
from src.tools.http_client import HttpResponse


def test_wildcard_without_credentials_is_suspected():
    obs = CorsMisconfiguration().detect(
        HttpResponse(200, {"Access-Control-Allow-Origin": "*"}, "http://localhost:3001")
    )
    assert obs["wildcard"] is True
    assert obs["with_credentials"] is False


def test_run_reports_suspected_for_bare_wildcard():
    class _Http:
        def get(self, url):
            return HttpResponse(200, {"access-control-allow-origin": "*"}, url)

    obs = CorsMisconfiguration().run(_Http(), "http://localhost:3001")
    assert obs["finding"]["confidence"] == "suspected"
    assert obs["finding"]["severity"] == "low"


def test_run_escalates_when_credentials_allowed():
    class _Http:
        def get(self, url):
            return HttpResponse(
                200,
                {"access-control-allow-origin": "*", "access-control-allow-credentials": "true"},
                url,
            )

    obs = CorsMisconfiguration().run(_Http(), "http://localhost:3001")
    assert obs["finding"]["confidence"] == "confirmed"
    assert obs["finding"]["severity"] == "high"


def test_specific_origin_is_not_flagged():
    obs = CorsMisconfiguration().detect(
        HttpResponse(200, {"Access-Control-Allow-Origin": "https://app.example"}, "http://x")
    )
    assert obs["wildcard"] is False
