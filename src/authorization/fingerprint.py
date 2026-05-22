"""Target identity verification.

The Nova incident showed why this matters: an authorization names a URL and an
expected application, but something else can be running there. Before testing,
the guard confirms the live target matches the authorization's expected_identity
markers — otherwise it fails closed. Identity verification is part of
authorization, not an optional add-on.
"""
from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

from src.tools.http_client import HttpResponse, urllib_fetch


@runtime_checkable
class Fingerprinter(Protocol):
    def matches(self, base_url: str, expected: dict) -> tuple[bool, str]:
        """Return (ok, detail). ok is True only if the live target matches."""
        ...


class HttpFingerprinter:
    """Confirms a live target matches an authorization's expected_identity.

    expected_identity keys:
      title_contains  - substring expected in the root page body/title
      marker_path     - a path that should exist on the expected application
      marker_contains - substring expected in the marker_path response body
    """

    def __init__(
        self,
        fetch: Callable[[str, float], HttpResponse] = urllib_fetch,
        timeout: float = 8.0,
    ) -> None:
        self.fetch = fetch
        self.timeout = timeout

    def matches(self, base_url: str, expected: dict) -> tuple[bool, str]:
        base = base_url.rstrip("/")
        try:
            root = self.fetch(base + "/", self.timeout)
        except Exception as exc:
            return False, f"could not fetch target root: {exc}"

        title = expected.get("title_contains")
        if title and title.lower() not in root.body.lower():
            return False, f"expected title_contains {title!r} not found at root"

        marker_path = expected.get("marker_path")
        if marker_path:
            try:
                marker = self.fetch(base + marker_path, self.timeout)
            except Exception as exc:
                return False, f"could not fetch marker {marker_path}: {exc}"
            if marker.status_code != 200:
                return False, f"marker {marker_path} returned {marker.status_code}"
            marker_contains = expected.get("marker_contains")
            if marker_contains and marker_contains.lower() not in marker.body.lower():
                return False, f"marker {marker_path} missing expected content {marker_contains!r}"

        return True, "identity confirmed"


class StaticFingerprinter:
    """Fixed-verdict fingerprinter for tests and offline dry-runs."""

    def __init__(self, ok: bool = True, detail: str = "static fingerprinter") -> None:
        self.ok = ok
        self.detail = detail

    def matches(self, base_url: str, expected: dict) -> tuple[bool, str]:
        return self.ok, self.detail
