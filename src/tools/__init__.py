"""Tools: gated I/O. The tool layer is the last line of defense — it refuses
unauthorized targets itself, not only via the orchestrator's guard."""
from .http_client import (
    HttpClient,
    HttpResponse,
    RateLimiter,
    UnauthorizedTargetError,
    fake_juice_shop_fetch,
    urllib_fetch,
)

__all__ = [
    "HttpClient",
    "HttpResponse",
    "RateLimiter",
    "UnauthorizedTargetError",
    "urllib_fetch",
    "fake_juice_shop_fetch",
]
