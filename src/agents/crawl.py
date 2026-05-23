"""Attack-surface discovery: a bounded, safe, GET-only crawler.

Maps an authorized target into a *surface* (pages, forms, parameterized endpoints)
so later phases have something to test. You cannot find a vuln in a page or
parameter you never discovered; this finds them.

Safety model:
- GET only. Forms are *recorded*, never submitted.
- Same-origin and within the authorized scope (the HttpClient gate is the real
  boundary; we also pre-filter to avoid noise).
- Bounded by max pages/depth and a per-page link cap; rate-limited by the shared
  client.
- Skips links that look state-changing (logout/delete/...). That list is
  best-effort, NOT a guarantee — the authorization (we only crawl targets we may
  test) is the actual safety boundary.

Static HTML only: a single-page app renders routes client-side, so a static
crawler sees ~one page. That is a structural limit (a headless browser is the
future fix), not a bug — CrawlResult.notes says so when it detects it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from urllib.parse import parse_qsl, urljoin, urlparse

if TYPE_CHECKING:
    from src.tools.http_client import HttpClient

_SKIP_PATTERNS_PATH = Path(__file__).with_name("crawler_skip_patterns.json")
_MAX_BODY = 500_000
_MAX_LINKS_PER_PAGE = 50


@dataclass
class CrawlResult:
    pages: list[dict] = field(default_factory=list)       # [{url, status, content_type, source}]
    forms: list[dict] = field(default_factory=list)       # [{action, method, params, found_on}]
    endpoints: list[dict] = field(default_factory=list)   # [{path, params, via, get_verified}]
    skipped: list[dict] = field(default_factory=list)     # [{url, reason}]
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "pages": len(self.pages),
            "forms": len(self.forms),
            "endpoints": len(self.endpoints),
            "params": sorted({p for e in self.endpoints for p in e["params"]}),
            "skipped": len(self.skipped),
        }


class _LinkFormParser(HTMLParser):
    """Extracts <a href>, <form> + its input/select/textarea names. Stdlib only."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.forms: list[dict] = []
        self.has_script = False
        self._form: Optional[dict] = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "script":
            self.has_script = True
        elif tag == "form":
            self._form = {"action": a.get("action", ""), "method": (a.get("method") or "get").lower(), "params": []}
        elif tag in ("input", "select", "textarea") and self._form is not None:
            if a.get("name"):
                self._form["params"].append(a["name"])

    def handle_endtag(self, tag):
        if tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None


def _load_skip_patterns() -> list[str]:
    try:
        return json.loads(_SKIP_PATTERNS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return ["logout", "signout", "sign-out", "delete", "remove", "destroy", "reset"]


def _norm_parts(url: str) -> tuple[str, str, str, list[str]]:
    """(scheme, netloc-without-default-port, path-without-trailing-slash, sorted param names)."""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    netloc = host
    if p.port and not ((p.scheme == "http" and p.port == 80) or (p.scheme == "https" and p.port == 443)):
        netloc = f"{host}:{p.port}"
    path = p.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    params = sorted({k for k, _ in parse_qsl(p.query)})
    return p.scheme, netloc, path, params


def _skippable(path: str, patterns: list[str]) -> bool:
    low = path.lower()
    return any(pat in low for pat in patterns)


def _add_endpoint(endpoints: dict, path: str, params: list[str], *, via: str, get_verified: bool) -> None:
    key = (path, tuple(sorted(params)))
    ep = endpoints.get(key)
    if ep is None:
        endpoints[key] = {"path": path, "params": sorted(params), "via": {via}, "get_verified": get_verified}
    else:
        ep["via"].add(via)
        ep["get_verified"] = ep["get_verified"] or get_verified


def _robots_disallow(http: "HttpClient", base: str) -> list[str]:
    try:
        resp = http.get(base + "/robots.txt")
    except Exception:
        return []
    if resp.status_code != 200:
        return []
    out = []
    for line in (resp.body or "").splitlines():
        line = line.strip()
        if line.lower().startswith("disallow:"):
            p = line.split(":", 1)[1].strip()
            if p.startswith("/") and "*" not in p:
                out.append(p)
    return out[:20]


def discover(
    http: "HttpClient",
    base_url: str,
    *,
    max_pages: int = 25,
    max_depth: int = 2,
    skip_patterns: Optional[list[str]] = None,
) -> CrawlResult:
    skip_patterns = skip_patterns if skip_patterns is not None else _load_skip_patterns()
    base = base_url.rstrip("/")
    base_netloc = _norm_parts(base + "/")[1]
    result = CrawlResult()
    endpoints: dict = {}
    visited: set = set()
    in_scope_links_found = False

    root_has_script = False
    queue: list[tuple[str, int, str]] = [(base + "/", 0, "seed")]
    for dis in _robots_disallow(http, base):
        queue.append((base + dis, 0, "robots"))

    while queue and len(result.pages) < max_pages:
        url, depth, source = queue.pop(0)
        _, netloc, path, params = _norm_parts(url)
        key = (netloc, path, tuple(params))
        if key in visited:
            continue
        visited.add(key)
        if netloc != base_netloc:
            result.skipped.append({"url": url, "reason": "out-of-scope"})
            continue
        if _skippable(path, skip_patterns):
            result.skipped.append({"url": url, "reason": "potential-side-effect"})
            continue
        try:
            resp = http.get(url)
        except Exception as exc:
            result.skipped.append({"url": url, "reason": f"fetch-failed:{type(exc).__name__}"})
            continue

        ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        result.pages.append({"url": url, "status": resp.status_code, "content_type": ctype, "source": source})
        _add_endpoint(endpoints, path, params, via=source if source == "robots" else "link", get_verified=True)

        if ctype and ctype != "text/html":
            continue

        parser = _LinkFormParser()
        try:
            parser.feed((resp.body or "")[:_MAX_BODY])
        except Exception:
            pass
        if source == "seed":
            root_has_script = parser.has_script

        for href in parser.links[:_MAX_LINKS_PER_PAGE]:
            absu = urljoin(url, href)
            if not absu.startswith(("http://", "https://")):
                continue
            _, n2, p2, pr2 = _norm_parts(absu)
            if n2 != base_netloc:
                result.skipped.append({"url": absu, "reason": "out-of-scope"})
                continue
            in_scope_links_found = True
            if pr2:
                _add_endpoint(endpoints, p2, pr2, via="link", get_verified=False)
            if _skippable(p2, skip_patterns):
                result.skipped.append({"url": absu, "reason": "potential-side-effect"})
                continue
            if (n2, p2, tuple(pr2)) not in visited and depth < max_depth:
                queue.append((absu, depth + 1, "link"))

        for form in parser.forms:
            action_abs = urljoin(url, form["action"])  # "" resolves to the current page
            _, fn, fp, _ = _norm_parts(action_abs)
            fparams = sorted(set(form["params"]))
            result.forms.append({"action": fp, "method": form["method"], "params": fparams, "found_on": path})
            if fn == base_netloc:
                _add_endpoint(endpoints, fp, fparams, via=f"form:{form['method']}", get_verified=False)

    result.endpoints = [
        {"path": e["path"], "params": e["params"], "via": sorted(e["via"]), "get_verified": e["get_verified"]}
        for e in endpoints.values()
    ]
    if root_has_script and not in_scope_links_found and not result.forms:
        result.notes.append(
            "appears to be a single-page application (scripts but no server-rendered "
            "links/forms); a static crawler cannot enumerate client-side routes — "
            "needs a headless browser"
        )
    return result
