"""Post-P1 Finding 3 — response_cache module tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.guard import response_cache as rc


def test_store_and_fetch_roundtrip():
    _mock = MagicMock()
    stored = {}
    def _set(k, v, ex=None):
        stored[k] = v
    _mock.set.side_effect = _set
    _mock.get.side_effect = lambda k: stored.get(k)
    with patch("app.guard.response_cache._redis_client", return_value=_mock):
        assert rc.store("req_1", 200, "application/json", b'{"ok":true}', ttl_seconds=60) is True
        got = rc.fetch("req_1")
        assert got is not None
        assert got.status_code == 200
        assert got.content_type == "application/json"
        assert got.body == b'{"ok":true}'


def test_fetch_returns_none_when_redis_unreachable():
    with patch("app.guard.response_cache._redis_client", return_value=None):
        assert rc.fetch("req_1") is None


def test_store_returns_false_when_redis_unreachable():
    with patch("app.guard.response_cache._redis_client", return_value=None):
        assert rc.store("req", 200, "text/plain", b"hi", ttl_seconds=60) is False


def test_fetch_returns_none_on_corrupt_entry():
    _mock = MagicMock()
    _mock.get.return_value = b"not-valid-json-envelope"
    with patch("app.guard.response_cache._redis_client", return_value=_mock):
        assert rc.fetch("req_1") is None


def test_fetch_returns_none_on_redis_exception():
    _mock = MagicMock()
    _mock.get.side_effect = RuntimeError("boom")
    with patch("app.guard.response_cache._redis_client", return_value=_mock):
        assert rc.fetch("req_1") is None


def test_cache_key_is_deterministic_and_namespaced():
    assert rc.cache_key("req_abc") == "guard:audit:response:req_abc"
