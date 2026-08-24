"""Unit tests for the ConductGuard HITL approval helpers (#1140).

Hermetic: no DB, no network, no LLM. Uses a pure-Python fake row + mock db.
Covers peer-check enforcement, timeout sweep, decision recording, and the
pending marker shape that CLI/MCP surfaces parse.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

_STUBS = ["structlog", "redis", "sentry_sdk", "app.core.pii"]
for _m in _STUBS:
    sys.modules.setdefault(_m, MagicMock())
# app.core.pii.redact_secrets must return its input (it is called by
# create_approval_request); the MagicMock default returns a MagicMock.
import app.core.pii as _pii  # noqa: E402
_pii.redact_secrets = lambda s: s

from app.modules.guard.approval import (  # noqa: E402
    approval_url,
    apply_decision,
    can_decide,
    pending_marker,
    sweep_if_timed_out,
)


# ── helpers ────────────────────────────────────────────────────────────────

def _row(**overrides):
    """Minimal fake row satisfying the attribute access apply_decision uses."""
    now = datetime.now(timezone.utc)
    base = {
        "id": "req-1",
        "workspace_id": "ws-1",
        "rule_id": "hipaa_phi_export_requires_approval",
        "rule_message": "PHI export requires approval",
        "tool_name": "bash",
        "requester_email": "alice@example.com",
        "requester_user_id": "user_alice",
        "surface": "claude_code",
        "source_run_id": None,
        "approval_type": "any_authorized",
        "status": "pending",
        "created_at": now,
        "timeout_at": now + timedelta(minutes=30),
        "decided_at": None,
        "decided_by_email": None,
        "decided_by_user_id": None,
        "decided_reason": None,
        "latency_ms": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeDB:
    """Just enough SQLAlchemy Session for apply_decision + sweep_if_timed_out.
    apply_decision commits + refreshes; both are no-ops here. add() is a no-op
    because we don't verify the audit-event insert path (that's covered by
    the existing GuardAuditEvent tests in test_guard.py)."""
    def __init__(self):
        self.committed = 0
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed += 1

    def refresh(self, obj):
        pass

    def query(self, *_a, **_k):
        # chain_hash_for_insert will hit this; return an empty query chain.
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.with_for_update.return_value = chain
        chain.first.return_value = None
        return chain


# ── peer check ─────────────────────────────────────────────────────────────

class TestCanDecide:
    def test_any_authorized_allows_any_role(self):
        row = _row(approval_type="any_authorized")
        ok, reason = can_decide(row, decider_email="bob@x.io", decider_user_id="u2", decider_role="developer")
        assert ok and reason is None

    def test_any_admin_rejects_non_admin(self):
        row = _row(approval_type="any_admin")
        ok, reason = can_decide(row, decider_email="bob@x.io", decider_user_id="u2", decider_role="security")
        assert not ok
        assert "admin" in reason

    def test_any_admin_allows_admin(self):
        row = _row(approval_type="any_admin")
        ok, reason = can_decide(row, decider_email="bob@x.io", decider_user_id="u2", decider_role="admin")
        assert ok

    def test_any_security_allows_admin_and_security(self):
        row = _row(approval_type="any_security")
        for role in ("admin", "security"):
            ok, _ = can_decide(row, decider_email="bob@x.io", decider_user_id="u2", decider_role=role)
            assert ok, f"role {role!r} should be allowed"

    def test_any_security_rejects_developer(self):
        row = _row(approval_type="any_security")
        ok, reason = can_decide(row, decider_email="bob@x.io", decider_user_id="u2", decider_role="developer")
        assert not ok
        assert "admins" in reason or "security" in reason

    def test_peer_blocks_self_by_email(self):
        row = _row(approval_type="peer", requester_email="alice@example.com", requester_user_id="u1")
        ok, reason = can_decide(row, decider_email="ALICE@example.com", decider_user_id="different", decider_role="admin")
        assert not ok
        assert "self" in reason or "peer" in reason

    def test_peer_blocks_self_by_user_id(self):
        row = _row(approval_type="peer", requester_email="", requester_user_id="u1")
        ok, reason = can_decide(row, decider_email="somebody@x.io", decider_user_id="u1", decider_role="admin")
        assert not ok

    def test_peer_allows_different_email(self):
        row = _row(approval_type="peer", requester_email="alice@example.com", requester_user_id="u1")
        ok, reason = can_decide(row, decider_email="bob@example.com", decider_user_id="u2", decider_role="admin")
        assert ok and reason is None

    def test_peer_refuses_when_requester_unknown(self):
        row = _row(approval_type="peer", requester_email=None, requester_user_id=None)
        ok, reason = can_decide(row, decider_email="bob@example.com", decider_user_id="u2", decider_role="admin")
        assert not ok

    def test_rejects_non_pending(self):
        row = _row(status="approved")
        ok, reason = can_decide(row, decider_email="bob@x.io", decider_user_id="u2", decider_role="admin")
        assert not ok
        assert "already" in reason


# ── timeout sweep ──────────────────────────────────────────────────────────

class TestTimeout:
    def test_no_sweep_when_still_pending(self):
        row = _row(timeout_at=datetime.now(timezone.utc) + timedelta(minutes=5))
        db = _FakeDB()
        out = sweep_if_timed_out(db, row)
        assert out.status == "pending"
        assert db.committed == 0

    def test_sweeps_expired_pending_to_timed_out(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        row = _row(
            created_at=past - timedelta(minutes=30),
            timeout_at=past,
        )
        db = _FakeDB()
        out = sweep_if_timed_out(db, row)
        assert out.status == "timed_out"
        assert out.decided_at is not None
        assert out.latency_ms is not None
        assert db.committed == 1

    def test_does_not_touch_already_decided(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        row = _row(status="approved", timeout_at=past)
        db = _FakeDB()
        out = sweep_if_timed_out(db, row)
        assert out.status == "approved"  # unchanged
        assert db.committed == 0


# ── decision recording ────────────────────────────────────────────────────

class TestApplyDecision:
    def test_records_approved(self):
        row = _row()
        db = _FakeDB()
        out = apply_decision(
            db, row,
            decision="approved",
            decider_email="bob@x.io",
            decider_user_id="u2",
            reason="minimum-necessary scope confirmed",
        )
        assert out.status == "approved"
        assert out.decided_by_email == "bob@x.io"
        assert out.decided_reason == "minimum-necessary scope confirmed"
        assert out.latency_ms is not None and out.latency_ms >= 0

    def test_records_rejected(self):
        row = _row()
        db = _FakeDB()
        out = apply_decision(
            db, row,
            decision="rejected",
            decider_email="bob@x.io",
            decider_user_id="u2",
            reason=None,
        )
        assert out.status == "rejected"
        assert out.decided_by_email == "bob@x.io"

    def test_rejects_invalid_decision(self):
        row = _row()
        db = _FakeDB()
        with pytest.raises(ValueError):
            apply_decision(
                db, row,
                decision="maybe",
                decider_email="bob@x.io",
                decider_user_id="u2",
                reason=None,
            )


# ── surface text ──────────────────────────────────────────────────────────

class TestPendingMarker:
    def test_shape(self):
        row = _row()
        text = pending_marker(row)
        # Hooks parse for these anchors — do not change without updating CLI.
        assert "PENDING approval" in text
        assert f"rule: {row.rule_id}" in text
        assert f"request: {row.id}" in text
        assert "timeout in" in text
        assert row.rule_message in text

    def test_url_helper(self):
        u = approval_url("req-abc")
        assert u.endswith("/theguard/approvals?highlight=req-abc")


# ── Endpoint validation branches (post humanised-copy commit) ──────────────
#
# The decide_approval() endpoint has two validation branches added to make
# the /theguard/approvals UI copy human-friendly:
#   1. Non-pending row → 409 with a per-status sentence (not the raw enum).
#   2. decision=rejected + missing/whitespace reason → 400.
# We call the endpoint function directly with all deps injected so we don't
# need TestClient just to exercise these tiny branches.

from unittest.mock import patch

from fastapi import HTTPException

from app.modules.guard.routers.approvals import DecisionIn, decide_approval


def _call_decide(row, body):
    """Invoke decide_approval() with every dependency injected explicitly.
    _get_row and sweep_if_timed_out are patched to passthrough — we only
    care about the validation branches added here."""
    db = _FakeDB()
    with patch(
        "app.modules.guard.routers.approvals._get_row", return_value=row
    ), patch(
        "app.modules.guard.routers.approvals.sweep_if_timed_out",
        side_effect=lambda db, r: r,
    ):
        return decide_approval(
            request_id=row.id,
            body=body,
            workspace_id=row.workspace_id,
            user_id="user_admin",
            role="admin",
            db=db,
            _="ok",  # require_permission stub
        )


class TestDecideEndpointRejectRequiresReason:
    """Backend enforcement of the UI 'Reason (required to reject)' rule.
    UI can be bypassed via curl; API is the source of truth."""

    def test_reject_without_reason_returns_400(self):
        row = _row(status="pending")
        with pytest.raises(HTTPException) as exc:
            _call_decide(row, DecisionIn(decision="rejected", reason=None))
        assert exc.value.status_code == 400
        assert "reason is required" in exc.value.detail.lower()

    def test_reject_with_whitespace_only_reason_returns_400(self):
        row = _row(status="pending")
        with pytest.raises(HTTPException) as exc:
            _call_decide(row, DecisionIn(decision="rejected", reason="   "))
        assert exc.value.status_code == 400

    def test_approve_without_reason_does_not_400(self):
        """Approve stays optional-reason — only reject requires one. We
        assert we get past the reason-required branch; anything downstream
        (fake-DB attribute errors, serialisation) is not our concern here."""
        row = _row(status="pending")
        try:
            _call_decide(row, DecisionIn(decision="approved", reason=None))
        except HTTPException as e:
            assert e.status_code != 400, (
                f"approve should not require a reason, got 400: {e.detail}"
            )
        except Exception:
            # Fake DB / SimpleNamespace can't fully serialize a DecisionOut.
            # That's fine — we only care that we didn't 400.
            pass


class TestDecideEndpointHumanised409:
    """Non-pending rows must surface human-readable copy, not raw enum values
    like 'approval already timed_out'."""

    @pytest.mark.parametrize(
        "status,expected_phrase",
        [
            ("approved", "already been approved"),
            ("rejected", "already been rejected"),
            ("timed_out", "already timed out"),
        ],
    )
    def test_known_non_pending_status_returns_specific_sentence(
        self, status, expected_phrase
    ):
        row = _row(status=status)
        with pytest.raises(HTTPException) as exc:
            _call_decide(row, DecisionIn(decision="approved", reason="ok"))
        assert exc.value.status_code == 409
        assert expected_phrase in exc.value.detail.lower(), (
            f"expected {expected_phrase!r} in message, got {exc.value.detail!r}"
        )

    def test_unknown_status_falls_back_to_generic_sentence(self):
        # If we ever add a new status without updating the phrase map we
        # must still produce a human-readable fallback, never the raw enum.
        row = _row(status="wat_is_this")
        with pytest.raises(HTTPException) as exc:
            _call_decide(row, DecisionIn(decision="approved", reason="ok"))
        assert exc.value.status_code == 409
        assert "no longer pending" in exc.value.detail.lower()


class TestDecideEndpointSecondClick:
    """Race condition: two admins click Approve/Reject in quick succession.
    The second click must return the humanised 409, not a generic error."""

    def test_second_click_after_approve_gets_human_409(self):
        # First decision succeeds (not modelled here). Second click arrives
        # after the row has status=approved.
        row = _row(status="approved", decided_by_email="alice@example.com")
        with pytest.raises(HTTPException) as exc:
            _call_decide(
                row, DecisionIn(decision="rejected", reason="changed my mind")
            )
        assert exc.value.status_code == 409
        assert "already been approved" in exc.value.detail.lower()

    def test_second_click_after_timeout_gets_human_409(self):
        row = _row(status="timed_out")
        with pytest.raises(HTTPException) as exc:
            _call_decide(row, DecisionIn(decision="approved", reason="ok"))
        assert exc.value.status_code == 409
        assert "already timed out" in exc.value.detail.lower()


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
