"""Recon: build an understanding of a target before testing it.

Two steps, mirroring the rest of the system: a deterministic *gather* (a few
safe, gated GETs) produces raw observations; a swappable *reasoner* turns those
into a SiteProfile (a summary, detected tech, security-relevant notes, and gaps
worth a new skill). The deterministic reasoner uses simple heuristics; the Claude
reasoner (when a key is set) reasons over the same observations. Gather never
ranges beyond a tiny, universally-safe set of recon paths.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools.http_client import HttpClient

# Universally-safe recon targets: the homepage and the crawler policy. Both are
# risk-1 GETs every recon methodology fetches. (LLM-directed crawling is a future
# extension; kept minimal here to stay safe and bounded.)
RECON_PATHS = ["/", "/robots.txt"]


@dataclass
class SiteProfile:
    target_url: str
    summary: str
    tech: list[str] = field(default_factory=list)
    observations: list[dict] = field(default_factory=list)   # [{path, status, notable[]}]
    gaps: list[dict] = field(default_factory=list)            # [{category, hint, path}]
    notes: list[str] = field(default_factory=list)


def gather(http: "HttpClient", target_url: str) -> list[dict]:
    """Fetch the safe recon set. Returns raw observations (headers + body head)."""
    base = target_url.rstrip("/")
    out: list[dict] = []
    for path in RECON_PATHS:
        try:
            resp = http.get(base + path)
        except Exception:
            continue
        out.append({
            "path": path,
            "status": resp.status_code,
            "headers": {k.lower(): v for k, v in resp.headers.items()},
            "body_head": (resp.body or "")[:2000],
        })
    return out


class RuleBasedRecon:
    """Heuristic understanding from observations — the deterministic fallback."""

    def understand(self, target_url: str, observations: list[dict]) -> SiteProfile:
        tech: list[str] = []
        notes: list[str] = []
        gaps: list[dict] = []
        obs_out: list[dict] = []

        for ob in observations:
            headers = ob.get("headers", {})
            body = ob.get("body_head", "")
            notable: list[str] = []

            if ob["path"] == "/":
                # Generic: surface whatever the response advertises about its stack.
                # (Not target-specific — works on any site; the LLM recon adds deeper
                # inference. Detection skills, not recon, do the vuln-finding.)
                if headers.get("server"):
                    tech.append(f"Server: {headers['server']}")
                if headers.get("x-powered-by"):
                    tech.append(f"X-Powered-By: {headers['x-powered-by']}")
                if "OWASP Juice Shop" in body:
                    tech.append("OWASP Juice Shop")
                if "content-security-policy" not in headers:
                    notable.append("no Content-Security-Policy")
                if headers.get("access-control-allow-origin") == "*":
                    notable.append("wildcard CORS")
                if headers.get("x-recruiting"):
                    notable.append("leaky X-Recruiting header")

            # A served robots.txt that discloses paths is a coverage gap if no
            # skill targets it — the seed for an autonomously-generated skill.
            if ob["path"] == "/robots.txt" and ob["status"] == 200 and "Disallow" in body:
                notable.append("robots.txt discloses paths")
                gaps.append({
                    "category": "crawler-policy-disclosure",
                    "hint": "robots.txt is served and discloses Disallow paths",
                    "path": "/robots.txt",
                })

            obs_out.append({"path": ob["path"], "status": ob["status"], "notable": notable})

        summary = (
            f"{target_url}: " + (", ".join(sorted(set(tech))) if tech else "unidentified stack")
            + f"; {sum(len(o['notable']) for o in obs_out)} security-relevant observation(s)"
        )
        return SiteProfile(target_url=target_url, summary=summary, tech=sorted(set(tech)),
                           observations=obs_out, gaps=gaps, notes=notes)
