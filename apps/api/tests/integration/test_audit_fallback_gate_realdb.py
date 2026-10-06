"""Real-DB integration for the Tier 2 audit-fallback completion gate (#2229).

Nightly-only per project convention — set ``RUN_ACCOUNTING_REALDB=1``.

Locks:
- ``count_audit_only_requests`` returns exactly the count the audit-fallback
  branches would sum from, so a zero return proves the fallback is dead
  code for that workspace / window.
- ``audit_only_by_workspace`` groups the same predicate by workspace.
- ``run_startup_gate`` fires the Slack notifier for workspaces with
  audit-only rows and stays silent when clean.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_ACCOUNTING_REALDB") != "1",
    reason="Real-DB test — set RUN_ACCOUNTING_REALDB=1 (nightly only).",
)


def _workspace():
    from app.core.database import SessionLocal
    from sqlalchemy import text

    ws_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO workspaces (id, name, owner_id, is_approved, plan) "
                "VALUES (CAST(:id AS uuid), :name, :owner, true, 'free')"
            ),
            {"id": ws_id, "name": f"gate-{ws_id[:8]}", "owner": "test-realdb"},
        )
        db.commit()
    yield ws_id
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM llm_attempt_receipts WHERE workspace_id = CAST(:id AS uuid)"),
            {"id": ws_id},
        )
        db.execute(
            text("DELETE FROM guard_audit_events WHERE workspace_id = CAST(:id AS uuid)"),
            {"id": ws_id},
        )
        db.execute(
            text("DELETE FROM workspaces WHERE id = CAST(:id AS uuid)"),
            {"id": ws_id},
        )
        db.commit()


@pytest.fixture
def workspace_id():
    yield from _workspace()


@pytest.fixture
def second_workspace_id():
    yield from _workspace()


def _insert_audit_only(
    workspace_id: str, *, ai_tool: str, request_id: str | None = None,
    ts: datetime | None = None,
) -> str:
    """Audit row with no matching receipt — the exact scenario the
    audit-fallback branches were built to catch."""
    from app.core.database import SessionLocal
    from sqlalchemy import text

    req_id = request_id or str(uuid.uuid4())
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO guard_audit_events "
                "(id, workspace_id, request_id, ts, source, provider, model, "
                " decision, cost_usd_after, ai_tool) "
                "VALUES (gen_random_uuid(), CAST(:ws AS uuid), CAST(:req AS uuid), "
                "        :ts, 'gateway', 'anthropic', 'claude-sonnet-4-6', "
                "        'allowed', 0.001, :ai_tool)"
            ),
            {"ws": workspace_id, "req": req_id, "ai_tool": ai_tool,
             "ts": ts or datetime.now(timezone.utc)},
        )
        db.commit()
    return req_id


def _insert_audit_with_receipt(workspace_id: str, *, ai_tool: str) -> str:
    """Audit row WITH matching receipt — must NOT count as audit-only."""
    from app.core.database import SessionLocal
    from app.runtime.accounting.shadow_writer import shadow_write
    from sqlalchemy import text

    req_id = uuid.uuid4()
    shadow_write(
        workspace_id=workspace_id,
        request_id=req_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',
        source="gateway",
        client_tool=ai_tool,
    )
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO guard_audit_events "
                "(id, workspace_id, request_id, ts, source, provider, model, "
                " decision, cost_usd_after, ai_tool) "
                "VALUES (gen_random_uuid(), CAST(:ws AS uuid), CAST(:req AS uuid), "
                "        now(), 'gateway', 'anthropic', 'claude-sonnet-4-6', "
                "        'allowed', 0.001, :ai_tool)"
            ),
            {"ws": workspace_id, "req": str(req_id), "ai_tool": ai_tool},
        )
        db.commit()
    return str(req_id)


# ─── count_audit_only_requests ────────────────────────────────────────


def test_count_zero_when_every_audit_has_a_receipt(workspace_id):
    """Every audit row has a matching receipt ⇒ gate == 0 ⇒ Tier 2
    deletion is safe."""
    from app.core.database import SessionLocal
    from app.runtime.accounting.audit_fallback_gate import (
        count_audit_only_requests,
    )

    ai_tool = f"gate-clean-{uuid.uuid4().hex[:8]}"
    _insert_audit_with_receipt(workspace_id, ai_tool=ai_tool)
    _insert_audit_with_receipt(workspace_id, ai_tool=ai_tool)

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        count = count_audit_only_requests(
            db, workspace_id=workspace_id, since=since
        )
    assert count == 0


def test_count_nonzero_when_audit_has_no_receipt(workspace_id):
    """An audit row without a matching receipt ⇒ gate > 0 ⇒
    Tier 2 deletion NOT yet safe."""
    from app.core.database import SessionLocal
    from app.runtime.accounting.audit_fallback_gate import (
        count_audit_only_requests,
    )

    ai_tool = f"gate-dirty-{uuid.uuid4().hex[:8]}"
    _insert_audit_only(workspace_id, ai_tool=ai_tool)

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        count = count_audit_only_requests(
            db, workspace_id=workspace_id, since=since
        )
    assert count == 1


# ─── audit_only_by_workspace ──────────────────────────────────────────


def test_audit_only_by_workspace_returns_only_dirty_workspaces(workspace_id):
    from app.core.database import SessionLocal
    from app.runtime.accounting.audit_fallback_gate import (
        audit_only_by_workspace,
    )

    # Seed at least one audit-only row so this workspace appears.
    _insert_audit_only(workspace_id, ai_tool=f"gate-list-{uuid.uuid4().hex[:8]}")

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        entries = audit_only_by_workspace(
            db, since=since, workspace_ids=[workspace_id]
        )
    assert len(entries) == 1
    assert entries[0].workspace_id == workspace_id
    assert entries[0].audit_only_count == 1
    assert entries[0].positive_cost_rows == 1
    assert entries[0].request_linked_rows == 1


# ─── run_startup_gate ─────────────────────────────────────────────────


def test_run_startup_gate_posts_single_platform_alert_for_dirty_fleet(workspace_id):
    """Gate emits ONE platform-operator alert via ``post_platform_alert``,
    which reads ``CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL`` (``#conduct-alerts``
    in prod) — no per-workspace spam. Fleet-wide signal, Conduct team is
    the audience."""
    from app.core.database import SessionLocal
    from app.runtime.accounting import audit_fallback_gate as gate_mod

    _insert_audit_only(
        workspace_id, ai_tool=f"gate-platform-{uuid.uuid4().hex[:8]}"
    )

    calls: list = []

    def _fake_platform_alert(*, surface: str, text: str, blocks=None):
        calls.append({"surface": surface, "text": text})
        return True

    # ``post_platform_alert`` is imported inside ``report_gate_to_slack``;
    # patch at the origin so the local import picks it up.
    with patch(
        "app.modules.guard.observability.platform_slack.post_platform_alert",
        _fake_platform_alert,
    ):
        result = gate_mod.run_startup_gate(SessionLocal)

    assert result["workspaces_with_audit_only"] >= 1
    assert result["slack_alert_sent"] is True
    assert result["ready_for_removal"] is False
    assert len(calls) == 1
    assert calls[0]["surface"] == "audit_fallback_gate"
    assert "audit-fallback still load-bearing" in calls[0]["text"]
    assert "#2229" in calls[0]["text"]
    assert workspace_id in calls[0]["text"]


def test_receipt_in_another_workspace_does_not_clear_gate(workspace_id, second_workspace_id):
    from app.core.database import SessionLocal
    from app.runtime.accounting.audit_fallback_gate import audit_only_by_workspace, count_audit_only_requests
    from app.runtime.accounting.shadow_writer import shadow_write

    req_id = uuid.uuid4()
    assert shadow_write(
        workspace_id=second_workspace_id, request_id=req_id, provider="anthropic",
        model="claude-sonnet-4-6", operation="messages.create", dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',
        source="gateway", client_tool="gate-other-workspace",
    ) is not None
    _insert_audit_only(workspace_id, ai_tool="gate-cross-workspace", request_id=str(req_id))
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        assert count_audit_only_requests(db, workspace_id=workspace_id, since=since) == 1
        entries = audit_only_by_workspace(db, since=since, workspace_ids=[workspace_id, second_workspace_id])
    assert [(e.workspace_id, e.audit_only_count) for e in entries] == [(workspace_id, 1)]


def test_prior_month_rows_inside_seven_days_block_removal(workspace_id):
    from app.core.database import SessionLocal
    from app.runtime.accounting.audit_fallback_gate import count_audit_only_requests, reporting_window_start

    now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    _insert_audit_only(workspace_id, ai_tool="gate-month-boundary", ts=now - timedelta(days=3))
    with SessionLocal() as db:
        assert count_audit_only_requests(db, workspace_id=workspace_id, since=reporting_window_start(now)) == 1


def test_null_request_hook_estimates_are_not_hidden(workspace_id):
    from app.core.database import SessionLocal
    from app.runtime.accounting.audit_fallback_gate import audit_only_by_workspace
    from sqlalchemy import text

    with SessionLocal() as db:
        db.execute(text("""
            INSERT INTO guard_audit_events (id, workspace_id, ts, source, ai_tool, decision, cost_usd_after)
            VALUES (gen_random_uuid(), CAST(:ws AS uuid), now(), 'hook', 'codex', 'allowed', 0.001)
        """), {"ws": workspace_id})
        db.commit()
        entries = audit_only_by_workspace(
            db, since=datetime.now(timezone.utc) - timedelta(hours=1), workspace_ids=[workspace_id],
        )
    assert len(entries) == 1
    assert entries[0].audit_only_count == entries[0].positive_cost_rows == 1
    assert entries[0].request_linked_rows == 0


def test_gate_transaction_rejects_writes(workspace_id):
    from app.core.database import SessionLocal
    from app.runtime.accounting import audit_fallback_gate as gate
    from sqlalchemy import text

    def attempt_write(db, **kwargs):
        db.execute(text("UPDATE workspaces SET name = 'must-not-change' WHERE id = CAST(:ws AS uuid)"),
                   {"ws": workspace_id})
        db.commit()
        return []

    with patch.object(gate, "audit_only_by_workspace", side_effect=attempt_write):
        result = gate.run_startup_gate(SessionLocal, notify=False)
    assert result["errors"] == 1
    assert result["ready_for_removal"] is False
    with SessionLocal() as db:
        name = db.execute(text("SELECT name FROM workspaces WHERE id = CAST(:ws AS uuid)"),
                          {"ws": workspace_id}).scalar_one()
    assert name != "must-not-change"
