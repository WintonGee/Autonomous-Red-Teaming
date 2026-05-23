"""Rate-limited, scope-enforcing HTTP client.

Defense in depth: `get()` refuses any URL outside the engagement's authorized
targets *itself*, so a code path that bypasses the orchestrator's guard still
fails closed. The actual network call is injected (`fetch`) so tests and
dry-runs need no live target.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional


@dataclass
class HttpResponse:
    status_code: int
    headers: dict
    url: str
    body: str = ""


class UnauthorizedTargetError(Exception):
    """Raised when a request is attempted against a non-authorized URL."""


Fetch = Callable[[str, float], HttpResponse]


class RateLimiter:
    """Simple spacing limiter: at most `max_rps` requests per second."""

    def __init__(
        self,
        max_rps: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = 1.0 / max_rps if max_rps > 0 else 0.0
        self._clock = clock
        self._sleep = sleep
        self._last: Optional[float] = None

    def acquire(self) -> None:
        if self.min_interval <= 0:
            return
        now = self._clock()
        if self._last is not None:
            wait = self.min_interval - (now - self._last)
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
        self._last = now


@dataclass
class HttpClient:
    allowed_urls: Iterable[str]
    fetch: Fetch
    rate_limiter: Optional[RateLimiter] = None
    timeout: float = 10.0
    _allowed: tuple = field(init=False, default=())

    def __post_init__(self) -> None:
        # Normalize authorized bases for prefix matching.
        self._allowed = tuple(u.rstrip("/") for u in self.allowed_urls)

    def _authorized(self, url: str) -> bool:
        u = url.rstrip("/")
        return any(u == base or u.startswith(base + "/") for base in self._allowed)

    def get(self, url: str) -> HttpResponse:
        if not self._authorized(url):
            raise UnauthorizedTargetError(
                f"refusing request to {url!r}: not within authorized targets {self._allowed}"
            )
        if self.rate_limiter is not None:
            self.rate_limiter.acquire()
        return self.fetch(url, self.timeout)


def urllib_fetch(url: str, timeout: float = 10.0) -> HttpResponse:
    """Real GET via the standard library. Used for live runs (e.g. Juice Shop).

    A non-2xx status is NOT an exception here: an error response is a valid
    response and is often the evidence itself (verbose 401/403/500 error pages).
    urlopen raises HTTPError on those, so we catch it and read its body. Only a
    true transport failure (connection refused, DNS, timeout) propagates as
    URLError for the caller to treat as 'unreachable'.
    """
    import http.client
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "art-lab/0.1"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 (lab use)
        status = resp.status
    except urllib.error.HTTPError as err:  # 4xx/5xx: keep the response + body
        resp = err
        status = err.code
    try:
        raw = resp.read()
    except http.client.IncompleteRead as exc:
        # Some endpoints (e.g. directory listings) mis-set Content-Length;
        # the body we did receive is still valid evidence.
        raw = exc.partial
    finally:
        resp.close()
    body = raw.decode("utf-8", errors="replace")
    headers = {k.lower(): v for k, v in resp.headers.items()}
    return HttpResponse(status_code=status, headers=headers, url=url, body=body)


# Headers the live Juice Shop returns on its root (recon 2026-05-21): note the
# wildcard CORS, the X-Recruiting leak, and the absence of CSP/HSTS/Referrer-Policy.
_FAKE_ROOT_HEADERS = {
    "content-type": "text/html; charset=UTF-8",
    "x-content-type-options": "nosniff",
    "x-frame-options": "SAMEORIGIN",
    "access-control-allow-origin": "*",
    "x-recruiting": "/#/jobs",
    "feature-policy": "payment 'self'",
}

_FAKE_ROUTES: dict[str, HttpResponse] = {
    # Real exposed files carry a content marker the SPA shell would never contain.
    # /ftp and /encryptionkeys are deliberately NOT modelled: like the live target,
    # they return the SPA index fallback (default branch below), so the marker-
    # requiring skill correctly does not report them.
    "/ftp/acquisitions.md": HttpResponse(
        200, {"content-type": "text/markdown"}, "",
        body="# Planned Acquisitions\nThis document is strictly confidential.\n"),
    "/ftp/legal.md": HttpResponse(200, {"content-type": "text/markdown"}, "",
                                  body="# Legal Information\nLorem ipsum.\n"),
    "/metrics": HttpResponse(200, {"content-type": "text/plain"}, "",
                             body="# HELP process_cpu_seconds_total ...\nprocess_cpu_seconds_total 1.0\n"),
    "/rest/admin/application-version": HttpResponse(
        200, {"content-type": "application/json"}, "", body='{"version":"20.0.0"}'),
    "/robots.txt": HttpResponse(200, {"content-type": "text/plain"}, "",
                                body="User-agent: *\nDisallow: /ftp\n"),
    # A request that triggers a verbose framework error page (stack-trace style).
    "/api/Feedbacks/99999": HttpResponse(
        401, {"content-type": "text/html"}, "",
        body="<html><head><title>UnauthorizedError: No Authorization header was "
             "found</title></head><body><pre>UnauthorizedError: No Authorization "
             "header was found\n    at /juice-shop/build/routes/verify.js:0:0</pre></body></html>"),
}


def fake_juice_shop_fetch(url: str, timeout: float = 10.0) -> HttpResponse:
    """Offline stand-in for the live Juice Shop, faithful to recon.

    Path-aware so every shipped skill exercises a realistic response offline:
    the root leaks headers + wildcard CORS and is missing CSP/HSTS/Referrer-Policy;
    /ftp, /metrics, /encryptionkeys and the version endpoint are exposed; a known
    error path returns a verbose error page. Any other path returns a root-like
    200 (so authorized-but-unmodelled paths still succeed in tests)."""
    from urllib.parse import urlparse

    path = urlparse(url).path.rstrip("/") or "/"
    if path in _FAKE_ROUTES:
        canned = _FAKE_ROUTES[path]
        return HttpResponse(canned.status_code, dict(canned.headers), url, canned.body)
    return HttpResponse(
        status_code=200,
        headers=dict(_FAKE_ROOT_HEADERS),
        url=url,
        body="<!DOCTYPE html><title>OWASP Juice Shop</title>",
    )
