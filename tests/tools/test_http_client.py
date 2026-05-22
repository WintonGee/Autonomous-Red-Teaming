import pytest

from src.tools.http_client import (
    HttpClient,
    RateLimiter,
    UnauthorizedTargetError,
    fake_juice_shop_fetch,
)


def test_refuses_unauthorized_target_at_tool_layer():
    client = HttpClient(allowed_urls={"http://localhost:3000"}, fetch=fake_juice_shop_fetch)
    with pytest.raises(UnauthorizedTargetError):
        client.get("http://evil.example.com/")


def test_allows_paths_under_authorized_base():
    client = HttpClient(allowed_urls={"http://localhost:3000"}, fetch=fake_juice_shop_fetch)
    resp = client.get("http://localhost:3000/rest/products")
    assert resp.status_code == 200


def test_rate_limiter_spaces_requests():
    slept: list[float] = []
    rl = RateLimiter(max_rps=2, clock=lambda: 100.0, sleep=slept.append)  # 0.5s spacing
    rl.acquire()   # first call: no wait
    rl.acquire()   # second call at same instant: must wait the full interval
    assert slept == [0.5]
