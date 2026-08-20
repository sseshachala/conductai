"""Unit tests for approval-resume verdict logic (MCP HITL loop fix).

Fills the coverage gap identified in the approval-surface audit: MCP
guard_check previously created a new pending request on every retry because
its filter was `status == 'pending'` only — an approver clicking "approve"
did not resume the agent. Fix in mcp.py routes through approval.resume_verdict
which handles approved/rejected/timed_out/pending/none uniformly.

These tests exercise the pure decision logic. The MCP-integration path is
covered by the api-matrix nightly job (test_mcp_endpoint_matrix).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
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
import app.core.pii as _pii  # noqa: E402
_pii.redact_secrets = lambda s: s

from app.modules.guard.approval import resume_verdict  # noqa: E402


class _Prior:
    """Minimal shape resume_verdict cares about."""
    def __init__(self, status: str):
        self.status = status


class TestResumeVerdict:
    def test_none_prior_creates_new_request(self):
        assert resume_verdict(None) == ("create", None)

    def test_approved_prior_proceeds(self):
        verdict, reason = resume_verdict(_Prior("approved"))
        assert verdict == "proceed"
        assert reason is None

    def test_rejected_prior_blocks_with_reason(self):
        verdict, reason = resume_verdict(_Prior("rejected"))
        assert verdict == "block"
        assert reason and "rejected" in reason.lower()

    def test_timed_out_prior_blocks_with_reason(self):
        verdict, reason = resume_verdict(_Prior("timed_out"))
        assert verdict == "block"
        assert reason and "timed out" in reason.lower()

    def test_pending_prior_returns_wait(self):
        assert resume_verdict(_Prior("pending")) == ("wait", None)

    def test_unknown_status_defaults_to_wait(self):
        # defensive: if the model ever grows a new status (e.g. "escalated"),
        # default to waiting rather than falsely allowing.
        assert resume_verdict(_Prior("escalated")) == ("wait", None)
