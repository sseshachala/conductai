"""ToolGuard core: verdict mapping + fail modes. No network."""
from __future__ import annotations

import asyncio

import pytest
from conduct_litellm_guard._client import GuardCheckClient

from conduct_agent_guard import ToolGuard


@pytest.fixture(autouse=True)
def _token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCT_AGENT_TOKEN", "cond_agt_test_placeholder")


def _respond(monkeypatch: pytest.MonkeyPatch, result: object) -> list[dict]:
    calls: list[dict] = []

    async def fake(self, **kwargs):  # noqa: ANN001
        calls.append(kwargs)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(GuardCheckClient, "guard_check_action", fake)
    return calls


async def test_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _respond(monkeypatch, "ok")
    v = await ToolGuard(surface="t").check("list_issues", {"repo": "a/b"})
    assert not v.blocked
    assert calls[0]["tool_name"] == "list_issues"
    assert calls[0]["tool_input"] == {"repo": "a/b"}


async def test_block_carries_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    _respond(monkeypatch, "BLOCKED — no repo deletes [rule: no-repo-delete]")
    v = await ToolGuard(surface="t").check("delete_repository", {"repo": "a/b"})
    assert v.blocked and v.decision.rule_id == "no-repo-delete"
    assert "no repo deletes" in v.reason


async def test_approval_blocks_with_clear_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _respond(monkeypatch, "PENDING approval — prod change [rule: prod-gate]")
    v = await ToolGuard(surface="t").check("deploy", {})
    assert v.blocked and v.reason.startswith("Requires human approval in Conduct")


async def test_warning_allows(monkeypatch: pytest.MonkeyPatch) -> None:
    _respond(monkeypatch, "WARNING — risky [rule: w]")
    assert not (await ToolGuard(surface="t").check("x", {})).blocked


async def test_unreachable_fails_closed_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _respond(monkeypatch, TimeoutError())
    assert (await ToolGuard(surface="t").check("x", {})).blocked


async def test_unreachable_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    _respond(monkeypatch, TimeoutError())
    assert not (await ToolGuard(surface="t", unreachable_fallback="fail_open").check("x", {})).blocked


def test_check_sync_outside_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    _respond(monkeypatch, "BLOCKED — no [rule: r]")
    assert ToolGuard(surface="t").check_sync("x", "raw-string-args").blocked


async def test_check_sync_inside_running_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    _respond(monkeypatch, "ok")
    assert asyncio.get_running_loop()
    assert not ToolGuard(surface="t").check_sync("x", {}).blocked


def test_missing_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONDUCT_AGENT_TOKEN")
    with pytest.raises(ValueError):
        ToolGuard(surface="t")
