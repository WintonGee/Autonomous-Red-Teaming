import http.client
from unittest.mock import patch

from src.tools.http_client import urllib_fetch


class _FakeResp:
    """Mimics urlopen's context manager, raising IncompleteRead on read()."""

    status = 200

    def __init__(self, partial: bytes) -> None:
        self._partial = partial
        self.headers = {"Content-Type": "text/html"}

    def read(self):
        raise http.client.IncompleteRead(self._partial, 12)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_incomplete_read_returns_partial_body():
    # Directory-listing endpoints mis-set Content-Length; we must keep the body
    # we received instead of dropping the response (which would hide the finding).
    with patch("urllib.request.urlopen", return_value=_FakeResp(b"Index of /ftp")):
        resp = urllib_fetch("http://localhost:3001/ftp")
    assert resp.status_code == 200
    assert "Index of /ftp" in resp.body
    assert resp.headers["content-type"] == "text/html"
