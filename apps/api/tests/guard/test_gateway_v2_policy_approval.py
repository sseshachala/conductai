"""Y1 — approval-action must NOT bypass per-target policy re-eval.

X1 (PR #2035) closed the alias-based BYPASS-via-BLOCK hole by
re-evaluating policy against ``target.model`` before each dispatch.
The initial fix only refused dispatch on ``pd.blocks`` (action=BLOCK).
An approval-action rule (``needs_approval``) still allowed the target
to be dispatched — an admin who set "approval required for gpt-4o"
could still see traffic reach gpt-4o via a ``cond-*`` alias.

Reproducer + fix:

- ``_build_policy_check`` now returns a ``PolicyBlock`` when
  ``pd.needs_approval`` is True, in addition to ``pd.blocks``.
- Reason string distinguishes the two so the audit row + 451 detail
  name whichever action fired.

Guardrails locked here:

- Approval-action target → coordinator skips it (records PolicyBlock).
- All-approval targets → same 451 as all-block targets (retrying
  won't help; the client needs the approval workflow, not another
  attempt).
- Warn-action target → still dispatches. WARN is advisory; the
  ingress eval already fired guidance/audit for it. If we refused
  on WARN we'd silently break every workspace that uses guidance-
  injection rules.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _pd(action_name: str, rule_id: str = "test-rule", reason: str = "test"):
    """Build a PolicyDecision with the requested action. Keeps the test
    honest against the real policy_types module — if PolicyAction gains
    or renames a member, this fails at import time."""
    from app.guard.policy_types import PolicyAction, PolicyDecision
    action = getattr(PolicyAction, action_name)
    return PolicyDecision(
        source="test",
        action=action,
        reason=reason,
        rule_id=rule_id,
    )


def _make_check(monkeypatch, fake_pd):
    """Build the closure with a stubbed ``evaluate_composed`` +
    ``SessionLocal`` + ``set_workspace_rls`` so we can drive it purely
    with a fixed PolicyDecision."""
    from app.modules.guard import gateway_handler

    # Stub out the DB session — we never actually query anything.
    class _FakeSession:
        def close(self): pass
    monkeypatch.setattr(
        "app.core.database.SessionLocal",
        lambda: _FakeSession(),
    )
    monkeypatch.setattr(
        "app.core.workspace_context.set_workspace_rls",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "app.guard.policy.evaluate_composed",
        lambda ctx: fake_pd,
    )
    return gateway_handler._build_policy_check(
        workspace_id="ws-1",
        clerk_user_id="u-1",
        agent_identity_id=None,
        fallback_provider="anthropic",
        body={"messages": []},
        risk_tier=None,
        ai_tool=None,
    )


def _fake_target(model: str = "claude-sonnet-4-6"):
    """Minimum shape the closure reads via getattr — no schema needed."""
    t = MagicMock()
    t.provider = "anthropic"
    t.integration = None
    t.model = model
    return t


def test_approval_action_returns_policy_block_not_none(monkeypatch):
    """Y1 REPRODUCER — before the fix, an approval-action rule
    against ``target.model`` returned None (allow dispatch), meaning
    an ``approval when model=gpt-4o`` rule could be bypassed by a
    ``cond-*`` alias resolving to gpt-4o. After the fix, the closure
    returns a PolicyBlock so the coordinator refuses this target."""
    from app.runtime.attempt_coordinator import PolicyBlock

    fake_pd = _pd("APPROVAL", rule_id="approval-gpt-4o", reason="needs approval")
    check = _make_check(monkeypatch, fake_pd)
    result = check(_fake_target(model="gpt-4o"))
    assert isinstance(result, PolicyBlock), (
        "approval-action target must return PolicyBlock to refuse dispatch — "
        "returning None allows the alias-bypass this PR was meant to close"
    )
    assert "approval" in result.message.lower() or result.rule_id == "approval-gpt-4o"


def test_block_action_still_returns_policy_block(monkeypatch):
    """Regression guard — the BLOCK path (the original X1 fix) still
    returns PolicyBlock. Together with the approval test above, this
    locks: block OR approval → refuse; anything else → allow."""
    from app.runtime.attempt_coordinator import PolicyBlock

    fake_pd = _pd("BLOCK", rule_id="block-sonnet", reason="model denied")
    check = _make_check(monkeypatch, fake_pd)
    result = check(_fake_target(model="claude-sonnet-4-6"))
    assert isinstance(result, PolicyBlock)
    assert result.rule_id == "block-sonnet"


def test_warn_action_returns_none_and_dispatch_proceeds(monkeypatch):
    """WARN is advisory — the ingress eval already fired guidance /
    audit for it. Refusing dispatch on WARN would break every
    workspace that uses guidance-injection rules, so the per-target
    re-eval MUST let WARN through."""
    fake_pd = _pd("WARN", rule_id="warn-verbose", reason="verbose model")
    check = _make_check(monkeypatch, fake_pd)
    assert check(_fake_target(model="gpt-4o")) is None, (
        "WARN action must not refuse per-target dispatch — the "
        "ingress eval already handled the guidance path"
    )


def test_allow_action_returns_none(monkeypatch):
    """ALLOW is the default happy path — closure returns None so the
    coordinator dispatches."""
    fake_pd = _pd("ALLOW")
    check = _make_check(monkeypatch, fake_pd)
    assert check(_fake_target()) is None


def test_approval_action_message_distinguishes_from_block(monkeypatch):
    """The audit row / 451 detail must be able to tell an approval-
    refuse from a block-refuse — same shape but different rule_id +
    message. Locks that distinction so dashboards can differentiate."""
    fake_pd = _pd("APPROVAL", rule_id="", reason="")
    check = _make_check(monkeypatch, fake_pd)
    result = check(_fake_target(model="gpt-4o"))
    assert result is not None
    # rule_id or message must contain a signal that this was
    # approval-based, not a plain block.
    assert (
        "approval" in (result.rule_id or "").lower()
        or "approval" in result.message.lower()
    ), f"approval refuse must be distinguishable from a block; got {result}"
