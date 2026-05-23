from src.agents.crawl import discover
from src.tools.http_client import HttpClient, HttpResponse
from urllib.parse import urlparse

BASE = "http://localhost:3001"

_PAGES = {
    "/": (
        '<html><body>'
        '<a href="/about">about</a>'
        '<a href="/search?q=hello">search</a>'
        '<a href="/search?q=world">search2</a>'   # same endpoint, different value -> dedupes
        '<a href="/logout">logout</a>'            # state-changing -> skipped
        '<a href="https://external.example/x">ext</a>'  # out-of-scope -> skipped
        '<form action="/login" method="post"><input name="username"><input name="password"></form>'
        '</body></html>'
    ),
    "/about": '<a href="/contact">contact</a><a href="/">home</a>',
    "/contact": '<form action="" method="get"><input name="email"></form>',   # action="" -> self
    "/search": '<html>results</html>',
}


def _fake(url, timeout=8.0):
    path = urlparse(url).path or "/"
    if path in _PAGES:
        return HttpResponse(200, {"content-type": "text/html"}, url, body=_PAGES[path])
    return HttpResponse(404, {"content-type": "text/html"}, url, body="not found")


def _http():
    return HttpClient(allowed_urls={BASE}, fetch=_fake)


def test_discovers_pages_forms_and_parameters():
    r = discover(_http(), BASE)
    paths = {urlparse(p["url"]).path for p in r.pages}
    assert {"/", "/about", "/contact"} <= paths

    login = next(f for f in r.forms if f["action"] == "/login")
    assert login["method"] == "post"
    assert login["params"] == ["password", "username"]

    search = next(e for e in r.endpoints if e["path"] == "/search")
    assert search["params"] == ["q"]
    assert search["get_verified"] is True


def test_query_endpoints_dedupe_by_path_and_param_names():
    r = discover(_http(), BASE)
    assert len([e for e in r.endpoints if e["path"] == "/search"]) == 1
    assert len([p for p in r.pages if urlparse(p["url"]).path == "/search"]) == 1


def test_form_action_empty_resolves_to_its_own_page():
    r = discover(_http(), BASE)
    contact_form = next(f for f in r.forms if "email" in f["params"])
    assert contact_form["action"] == "/contact"
    assert contact_form["method"] == "get"


def test_form_endpoint_is_declared_not_get_verified():
    r = discover(_http(), BASE)
    login_ep = next(e for e in r.endpoints if e["path"] == "/login")
    assert "form:post" in login_ep["via"]
    assert login_ep["get_verified"] is False        # never GET'd; only declared


def test_skips_state_changing_and_out_of_scope_links():
    r = discover(_http(), BASE)
    reasons = {s["reason"] for s in r.skipped}
    assert "potential-side-effect" in reasons        # /logout
    assert "out-of-scope" in reasons                 # external.example
    assert all(urlparse(p["url"]).path != "/logout" for p in r.pages)


def test_respects_max_pages_bound():
    r = discover(_http(), BASE, max_pages=2)
    assert len(r.pages) <= 2


def test_notes_single_page_application():
    def spa(url, timeout=8.0):
        return HttpResponse(200, {"content-type": "text/html"}, url,
                            body="<html><head><script src='/main.js'></script></head><body>app</body></html>")
    r = discover(HttpClient(allowed_urls={BASE}, fetch=spa), BASE)
    assert any("single-page application" in n for n in r.notes)
