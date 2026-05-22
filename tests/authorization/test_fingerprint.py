from src.authorization import HttpFingerprinter
from src.tools.http_client import HttpResponse

EXPECTED = {
    "title_contains": "OWASP Juice Shop",
    "marker_path": "/rest/admin/application-version",
    "marker_contains": "version",
}


def _juice_shop_fetch(url, timeout=8.0):
    if url.endswith("/rest/admin/application-version"):
        return HttpResponse(200, {}, url, '{"version":"20.0.0"}')
    return HttpResponse(200, {}, url, "<title>OWASP Juice Shop</title>")


def _nova_fetch(url, timeout=8.0):
    return HttpResponse(200, {}, url, "<title>Nova — Personal Assistant</title>")


def test_matches_real_juice_shop():
    ok, detail = HttpFingerprinter(fetch=_juice_shop_fetch).matches("http://localhost:3001", EXPECTED)
    assert ok is True, detail


def test_rejects_wrong_app_at_url():
    ok, detail = HttpFingerprinter(fetch=_nova_fetch).matches("http://localhost:3001", EXPECTED)
    assert ok is False
    assert "title_contains" in detail


def test_rejects_when_marker_missing():
    def fetch(url, timeout=8.0):
        if url.endswith("/rest/admin/application-version"):
            return HttpResponse(404, {}, url, "")
        return HttpResponse(200, {}, url, "<title>OWASP Juice Shop</title>")

    ok, detail = HttpFingerprinter(fetch=fetch).matches("http://localhost:3001", EXPECTED)
    assert ok is False
    assert "marker" in detail
