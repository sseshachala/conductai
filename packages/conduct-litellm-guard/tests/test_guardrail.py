"""Unit tests for ``ConductGuard`` — no network, no real LiteLLM."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest

from conduct_litellm_guard import ConductGuard, GuardDecision
from conduct_litellm_guard.guardrail import ConductGuardBlocked


# ── Decision parsing ────────────────────────────────────────────────────


class TestGuardDecisionParse:
    """String-envelope parsing owns half the surface area of the plugin.
    Keeping every branch covered guards us against subtle upstream changes
    in the guard_check response contract."""

    @pytest.mark.parametrize("raw", ["ok", "OK", "", "  ok "])
    def test_ok_variants_are_allow(self, raw: str) -> None:
        assert GuardDecision.parse(raw).verdict == "allow"

    def test_blocked_extracts_rule_id(self) -> None:
        d = GuardDecision.parse(
            "BLOCKED — command touches /etc/passwd  [rule: no-etc-passwd]"
        )
        assert d.verdict == "block"
        assert d.rule_id == "no-etc-passwd"
        assert "touches /etc/passwd" in d.message

    def test_pending_approval_treated_as_block(self) -> None:
        d = GuardDecision.parse(
            "PENDING approval — HITL required [rule: prod-deploy-gate]"
        )
        assert d.verdict == "approval"
        assert d.rule_id == "prod-deploy-gate"

    def test_warning_is_warning(self) -> None:
        d = GuardDecision.parse(
            "WARNING — high-risk model requested [rule: model-risk-tier]"
        )
        assert d.verdict == "warning"
        assert d.rule_id == "model-risk-tier"

    def test_advisory_is_advisory(self) -> None:
        d = GuardDecision.parse(
            "advisory: policy eval error (fail-open): boom"
        )
        assert d.verdict == "advisory"

    def test_unknown_prefix_marked_unknown(self) -> None:
        d = GuardDecision.parse("something the server invented later")
        assert d.verdict == "unknown"

    def test_ws_prefix_and_bracket_rule_regression(self) -> None:
        """Server wraps tool responses with '[ws:xxxxxxxx] ' for debug context
        (apps/api/app/modules/guard/routers/mcp.py:_text). Without stripping,
        every verdict falls through to 'unknown' and BLOCKED never fires."""
        raw = (
            "[ws:fd4b6608] BLOCKED — Account deletion needs a workspace "
            "admin's approval. │  [rule: account-deletion-needs-approval]"
        )
        d = GuardDecision.parse(raw)
        assert d.verdict == "block"
        assert d.rule_id == "account-deletion-needs-approval"
        assert d.message and "Account deletion" in d.message



# ── Pre-call hook ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _agent_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every ``ConductGuard()`` construction needs an agent token. We
    inject a placeholder so tests can build the object without real
    credentials."""
    monkeypatch.setenv("CONDUCT_AGENT_TOKEN", "cond_agt_test_placeholder")


def _guard(**overrides) -> ConductGuard:
    g = ConductGuard(**overrides)
    # Every test stubs the transport — no real HTTP fires.
    g._client.guard_check = AsyncMock(return_value=overrides.pop("_response", "ok"))
    return g


class TestPreCallHook:
    async def test_allow_returns_data_with_metadata_tag(self) -> None:
        g = _guard()
        g._client.guard_check = AsyncMock(return_value="ok")
        data = {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}
        result = await g.async_pre_call_hook(None, None, data, "completion")
        assert result is data
        assert result["metadata"]["conduct_guard"]["verdict"] == "allow"

    async def test_block_raises(self) -> None:
        g = _guard()
        g._client.guard_check = AsyncMock(
            return_value="BLOCKED — no prod secrets in prompt [rule: no-prod-secrets]"
        )
        data = {"model": "gpt-4o", "messages": [{"role": "user", "content": "AKIA..."}]}
        with pytest.raises(ConductGuardBlocked) as exc:
            await g.async_pre_call_hook(None, None, data, "completion")
        assert exc.value.decision.rule_id == "no-prod-secrets"

    async def test_pending_approval_also_raises(self) -> None:
        """PENDING approval must block the request while HITL runs — the
        LiteLLM caller cannot wait indefinitely."""
        g = _guard()
        g._client.guard_check = AsyncMock(
            return_value="PENDING approval — please review [rule: prod-gate]"
        )
        with pytest.raises(ConductGuardBlocked):
            await g.async_pre_call_hook(None, None, {}, "completion")


class TestFailModes:
    async def test_fail_closed_blocks_on_network_error(self) -> None:
        g = ConductGuard(fail_mode="fail_closed")
        g._client.guard_check = AsyncMock(side_effect=RuntimeError("connection refused"))
        decision = await g.check(data={}, call_type="completion")
        assert decision.verdict == "block"

    async def test_fail_open_allows_on_network_error(self) -> None:
        g = ConductGuard(fail_mode="fail_open")
        g._client.guard_check = AsyncMock(side_effect=RuntimeError("connection refused"))
        decision = await g.check(data={}, call_type="completion")
        assert decision.verdict == "allow"

    async def test_missing_token_raises_at_construction(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CONDUCT_AGENT_TOKEN", raising=False)
        with pytest.raises(ValueError, match="agent_token"):
            ConductGuard()


# ── Session-ID chain ───────────────────────────────────────────────────


class TestSessionIdExtraction:
    """The chain: litellm_metadata.trace_id → X-Conduct-Session-Id →
    hash(user + first_message). Documented in README."""

    async def test_prefers_trace_id_from_litellm_metadata(self) -> None:
        g = _guard()
        capture: dict = {}

        async def _capture(**kwargs):
            capture.update(kwargs)
            return "ok"

        g._client.guard_check = _capture  # type: ignore[assignment]
        await g.check(
            data={"litellm_metadata": {"trace_id": "trace-abc"}},
            call_type="completion",
        )
        assert capture["session_id"] == "trace-abc"

    async def test_fallback_to_conduct_session_id_header(self) -> None:
        g = _guard()
        capture: dict = {}

        async def _capture(**kwargs):
            capture.update(kwargs)
            return "ok"

        g._client.guard_check = _capture  # type: ignore[assignment]
        await g.check(
            data={"metadata": {"X-Conduct-Session-Id": "explicit-session"}},
            call_type="completion",
        )
        assert capture["session_id"] == "explicit-session"

    async def test_hash_fallback_when_no_metadata(self) -> None:
        g = _guard()
        capture: dict = {}

        async def _capture(**kwargs):
            capture.update(kwargs)
            return "ok"

        g._client.guard_check = _capture  # type: ignore[assignment]
        await g.check(
            data={
                "user": "alice@example.com",
                "messages": [{"role": "user", "content": "hello"}],
            },
            call_type="completion",
        )
        # Deterministic prefix + non-empty hash → same input yields same id.
        assert capture["session_id"] is not None
        assert capture["session_id"].startswith("litellm-")


if __name__ == "__main__":
    import subprocess
    import sys
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
