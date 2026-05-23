import http.client
import io
import urllib.error
from unittest.mock import patch

from src.tools.http_client import urllib_fetch


class _FakeResp:
    """Mimics urlopen's return value, raising IncompleteRead on read()."""

    status = 200

    def __init__(self, partial: bytes) -> None:
        self._partial = partial
        self.headers = {"Content-Type": "text/html"}

    def read(self):
        raise http.client.IncompleteRead(self._partial, 12)

    def close(self):
        pass


def test_incomplete_read_returns_partial_body():
    # Directory-listing endpoints mis-set Content-Length; we must keep the body
    # we received instead of dropping the response (which would hide the finding).
    with patch("urllib.request.urlopen", return_value=_FakeResp(b"Index of /ftp")):
        resp = urllib_fetch("http://localhost:3001/ftp")
    assert resp.status_code == 200
    assert "Index of /ftp" in resp.body
    assert resp.headers["content-type"] == "text/html"


def test_error_status_body_is_captured_not_raised():
    # A 401/500 error page is valid evidence (verbose errors live here). urlopen
    # raises HTTPError on those; urllib_fetch must capture the status + body.
    err = urllib.error.HTTPError(
        url="http://localhost:3001/api/Feedbacks/99999",
        code=401,
        msg="Unauthorized",
        hdrs={"Content-Type": "text/html"},
        fp=io.BytesIO(b"UnauthorizedError: No Authorization header\n    at verify.js:1:1"),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        resp = urllib_fetch("http://localhost:3001/api/Feedbacks/99999")
    assert resp.status_code == 401
    assert "UnauthorizedError" in resp.body
