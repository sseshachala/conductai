"""Cache-first credential fetch — kills the intermittent MissingProviderKey
on run resume.

Before: every block called fetch_credential -> HTTP broker call. Any
non-200 (broker restart, cred_token invalidated by prior segment) got
swallowed as {} and looked identical to "no key configured", so
brain_block raised MissingProviderKey and blamed the user's env.

After: executor populates a process-local snapshot at run init. Blocks
read the snapshot; broker is fallback for CLI / out-of-process only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

for _m in ["structlog", "redis", "sentry_sdk", "app.core.pii"]:
    sys.modules.setdefault(_m, MagicMock())

from app.runtime import run_credentials  # noqa: E402
from app.core.credentials import fetch_credential  # noqa: E402


class TestCacheLifecycle:
    def test_populate_then_resolve_returns_snapshot(self):
        run_credentials.populate("cond_cred_test_1", {"anthropic": {"api_key": "sk-real"}})
        assert run_credentials.resolve("cond_cred_test_1", "anthropic") == {"api_key": "sk-real"}
        run_credentials.purge("cond_cred_test_1")

    def test_purge_evicts_snapshot(self):
        run_credentials.populate("cond_cred_test_2", {"anthropic": {"api_key": "sk-x"}})
        run_credentials.purge("cond_cred_test_2")
        assert run_credentials.resolve("cond_cred_test_2", "anthropic") is None

    def test_resolve_miss_returns_none_not_empty_dict(self):
        # Callers distinguish "not cached" (None -> fall back to broker) from
        # "explicitly empty handle" ({} -> handle exists but has no fields).
        assert run_credentials.resolve("cond_cred_never_populated", "anthropic") is None

    def test_populate_with_empty_token_is_noop(self):
        # Guards against caching under "" key which would pollute the cache
        # for every subsequent empty-token call.
        run_credentials.populate("", {"anthropic": {"api_key": "leak"}})
        assert run_credentials.resolve("", "anthropic") is None


class TestFetchCredentialCacheFirst:
    def test_cache_hit_skips_httpx_call(self):
        run_credentials.populate("cond_cred_hot_1", {"anthropic": {"api_key": "sk-cached"}})
        try:
            with patch("httpx.post") as mock_post:
                result = fetch_credential("cond_cred_hot_1", "anthropic", "http://api")
                assert result == {"api_key": "sk-cached"}
                mock_post.assert_not_called()
        finally:
            run_credentials.purge("cond_cred_hot_1")

    def test_cache_miss_falls_back_to_broker(self):
        with patch("httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"api_key": "sk-broker"}
            result = fetch_credential("cond_cred_miss", "anthropic", "http://api")
            assert result == {"api_key": "sk-broker"}
            mock_post.assert_called_once()

    def test_broker_non_200_returns_empty(self):
        # Existing behaviour — brain_block's fallback ladder still handles
        # empty. The new log line (not asserted here) makes the failure
        # visible for operators.
        with patch("httpx.post") as mock_post:
            mock_post.return_value.status_code = 401
            result = fetch_credential("cond_cred_bad_token", "anthropic", "http://api")
            assert result == {}

    def test_broker_exception_returns_empty_instead_of_crashing(self):
        with patch("httpx.post", side_effect=Exception("connection reset")):
            result = fetch_credential("cond_cred_exc", "anthropic", "http://api")
            assert result == {}
