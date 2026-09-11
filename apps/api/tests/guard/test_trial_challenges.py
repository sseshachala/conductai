"""Unit tests for the trial-challenge Redis store + trusted-proxy IP parser
(audit S01 + S12).

These tests don't touch FastAPI; they exercise the primitives directly so
regressions in mint/redeem semantics or XFF handling show up early.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# ── mint / redeem round-trip ────────────────────────────────────────────────

class _FakeRedis:
    """In-memory shim for the tiny subset of redis-py we use."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    def getdel(self, key: str):
        return self.store.pop(key, None)

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, r: _FakeRedis):
        self.r = r
        self.ops: list = []

    def incr(self, key: str, n: int = 1):
        self.ops.append(("incr", key, n))
        return self

    def expire(self, key: str, ttl: int):
        self.ops.append(("expire", key, ttl))
        return self

    def execute(self):
        results = []
        for op in self.ops:
            if op[0] == "incr":
                _, key, n = op
                cur = int(self.r.store.get(key, 0)) + n
                self.r.store[key] = str(cur)
                results.append(cur)
            else:
                results.append(1)
        self.ops = []
        return results


def test_mint_returns_none_when_redis_unavailable():
    from app.modules.guard import trial_challenges as tc
    with patch.object(tc, "_redis", return_value=None):
        assert tc.mint("user@example.com", "Acme", None) is None


def test_mint_redeem_roundtrip_preserves_challenge_fields():
    from app.modules.guard import trial_challenges as tc
    fake = _FakeRedis()
    with patch.object(tc, "_redis", return_value=fake):
        token = tc.mint("user@example.com", "Acme", "user_abc")
        assert token
        ch = tc.redeem(token)
        assert ch is not None
        assert ch.email == "user@example.com"
        assert ch.company == "Acme"
        assert ch.existing_user_id == "user_abc"


def test_redeem_is_single_use():
    from app.modules.guard import trial_challenges as tc
    fake = _FakeRedis()
    with patch.object(tc, "_redis", return_value=fake):
        token = tc.mint("user@example.com", "Acme", None)
        first = tc.redeem(token)
        second = tc.redeem(token)
        assert first is not None
        assert second is None       # GETDEL consumed on first call


def test_redeem_unknown_token_returns_none():
    from app.modules.guard import trial_challenges as tc
    fake = _FakeRedis()
    with patch.object(tc, "_redis", return_value=fake):
        assert tc.redeem("not-a-real-token") is None


def test_rate_checks_fail_closed_without_redis():
    """Audit S12 — no free issuance when abuse controls aren't in effect."""
    from app.modules.guard import trial_challenges as tc
    with patch.object(tc, "_redis", return_value=None):
        assert tc.check_email_rate("user@example.com") is False
        assert tc.check_global_rate() is False


def test_email_rate_allows_first_calls_then_blocks():
    from app.modules.guard import trial_challenges as tc
    fake = _FakeRedis()
    with patch.object(tc, "_redis", return_value=fake):
        assert tc.check_email_rate("user@example.com") is True    # 1
        assert tc.check_email_rate("user@example.com") is True    # 2
        assert tc.check_email_rate("user@example.com") is True    # 3 (cap)
        assert tc.check_email_rate("user@example.com") is False   # 4 blocked


# ── client_ip_from — audit S12 trusted-proxy walking ──────────────────────

def _mk_request(*, xff: str | None, client_host: str):
    headers = {"x-forwarded-for": xff} if xff else {}
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host=client_host),
    )


def test_client_ip_ignores_xff_when_no_trusted_cidrs():
    """No TRUSTED_PROXY_CIDRS = blind trust would let anyone forge X-Forwarded-For."""
    from app.modules.guard import trial_challenges as tc
    with patch("app.modules.guard.trial_challenges.settings",
               SimpleNamespace(trusted_proxy_cidrs="")):
        req = _mk_request(xff="1.2.3.4, 5.6.7.8", client_host="10.0.0.5")
        assert tc.client_ip_from(req) == "10.0.0.5"


def test_client_ip_walks_xff_from_right_when_trusted_cidrs_set():
    """With trusted CIDRs configured, walk XFF from right and return the
    first non-trusted hop — that's the real client behind the LB."""
    from app.modules.guard import trial_challenges as tc
    with patch("app.modules.guard.trial_challenges.settings",
               SimpleNamespace(trusted_proxy_cidrs="10.0.0.0/8")):
        # attacker at 1.2.3.4 → LB1 (10.0.0.5) → LB2 (10.0.0.6) → us
        req = _mk_request(xff="1.2.3.4, 10.0.0.5, 10.0.0.6", client_host="10.0.0.6")
        assert tc.client_ip_from(req) == "1.2.3.4"


def test_client_ip_falls_back_when_all_hops_trusted():
    from app.modules.guard import trial_challenges as tc
    with patch("app.modules.guard.trial_challenges.settings",
               SimpleNamespace(trusted_proxy_cidrs="10.0.0.0/8")):
        req = _mk_request(xff="10.0.0.5, 10.0.0.6", client_host="10.0.0.6")
        # Leftmost hop returned + warning logged. Test just checks non-crash.
        assert tc.client_ip_from(req) == "10.0.0.5"


def test_client_ip_falls_back_when_xff_missing():
    from app.modules.guard import trial_challenges as tc
    with patch("app.modules.guard.trial_challenges.settings",
               SimpleNamespace(trusted_proxy_cidrs="10.0.0.0/8")):
        req = _mk_request(xff=None, client_host="203.0.113.5")
        assert tc.client_ip_from(req) == "203.0.113.5"


def test_client_ip_ignores_malformed_xff_hop():
    from app.modules.guard import trial_challenges as tc
    with patch("app.modules.guard.trial_challenges.settings",
               SimpleNamespace(trusted_proxy_cidrs="10.0.0.0/8")):
        req = _mk_request(xff="1.2.3.4, not-an-ip, 10.0.0.5", client_host="10.0.0.5")
        assert tc.client_ip_from(req) == "1.2.3.4"
