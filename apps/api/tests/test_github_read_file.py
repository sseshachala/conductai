"""
github.read_file unit tests — mock httpx so we don't talk to GitHub.
"""
import base64
from unittest.mock import MagicMock, patch

from app.runtime.integrations import github


def _fake_get(*, status_code: int = 200, json_body=None):
    """Return a MagicMock that mimics httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.raise_for_status.return_value = None
    return resp


def test_read_file_returns_decoded_content():
    encoded = base64.b64encode(b"name: test\n").decode("ascii")
    response = _fake_get(
        json_body={
            "path": "delegator.yml",
            "content": encoded,
            "encoding": "base64",
            "sha": "abc123",
            "size": 11,
        }
    )
    with patch.object(github.httpx, "get", return_value=response):
        out = github.read_file(token="t", owner="o", repo="r", path="delegator.yml")
    assert out["found"] is True
    assert out["content"] == "name: test\n"
    assert out["sha"] == "abc123"


def test_read_file_returns_found_false_on_404():
    response = _fake_get(status_code=404)
    with patch.object(github.httpx, "get", return_value=response):
        out = github.read_file(token="t", owner="o", repo="r", path="missing.yml")
    assert out == {"found": False, "path": "missing.yml", "ref": None}


def test_read_file_handles_directory_response_gracefully():
    """GitHub returns a list when the path is a directory. We must not crash."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = [{"name": "file1"}, {"name": "file2"}]
    resp.raise_for_status.return_value = None
    with patch.object(github.httpx, "get", return_value=resp):
        out = github.read_file(token="t", owner="o", repo="r", path="some-dir")
    assert out["found"] is False
    assert "directory" in out.get("reason", "")
