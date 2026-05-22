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
    """Real GET via the standard library. Used for live runs (e.g. Juice Shop)."""
    import urllib.request

    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "art-lab/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (lab use)
        body = resp.read().decode("utf-8", errors="replace")
        headers = {k.lower(): v for k, v in resp.headers.items()}
        return HttpResponse(status_code=resp.status, headers=headers, url=url, body=body)


def fake_juice_shop_fetch(url: str, timeout: float = 10.0) -> HttpResponse:
    """Offline stand-in: a response that is missing several security headers."""
    return HttpResponse(
        status_code=200,
        headers={"x-content-type-options": "nosniff", "server": "nginx"},
        url=url,
        body="<!DOCTYPE html><title>OWASP Juice Shop</title>",
    )
