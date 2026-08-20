"""Unit tests for the runtime approval-resume path in guard_block.

Runtime approval flow:
  1. guard_block sees a rule with action=approval → creates GuardApprovalRequest
     and raises ApprovalRequired (see blocks/guard_block.py).
  2. dag_runner catches ApprovalRequired → pauses the run.
  3. Approver POSTs a decision to /guard/approvals/{id} — the approvals router
     writes state[__approval_<block_id>] = "approved"|"rejected" and re-enqueues
     the run.
  4. dag_runner resumes and re-executes the paused guard block.

Before this fix step 4 would re-fire the same rule and create ANOTHER pending
request — the loop never completed at runtime. Fix adds a resume-check at the
top of _execute_guard that consumes the state marker: approved returns a
resumed_approved status without re-evaluating rules; rejected raises.

Mirrors the runtime approval_block resume pattern (see blocks/approval_block.py).
"""
from __future__ import annotations

import os
import sys
import uuid
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

for _m in ["structlog", "redis", "sentry_sdk", "app.core.pii"]:
    sys.modules.setdefault(_m, MagicMock())

# Import the block-level function directly (not the executor re-export) —
# these tests only exercise the resume-check branch that fires before any
# rule iteration or DB access.
from app.runtime.blocks.guard_block import _execute_guard  # noqa: E402


def _cache():
    return {"workspace_id": str(uuid.uuid4()), "policies": [], "enforcement_mode": "block"}


class TestRuntimeApprovalResume:
    def test_approved_state_returns_resumed_and_clears_marker(self):
        block = {"id": "guard_pre_brain_1"}
        state = {"__approval_guard_pre_brain_1": "approved", "other": "keep"}
        result = _execute_guard(
            block, state, workspace_id=str(uuid.uuid4()), db=MagicMock(),
            _policy_cache=_cache(),
        )
        assert result["status"] == "resumed_approved"
        assert result["block_id"] == "guard_pre_brain_1"
        # marker must be consumed so subsequent auto-guard passes evaluate fresh
        assert "__approval_guard_pre_brain_1" not in state
        assert state["other"] == "keep"

    def test_rejected_state_raises_and_clears_marker(self):
        block = {"id": "guard_pre_brain_1"}
        state = {"__approval_guard_pre_brain_1": "rejected"}
        with pytest.raises(RuntimeError, match=r"Approval rejected for guard block 'guard_pre_brain_1'"):
            _execute_guard(
                block, state, workspace_id=str(uuid.uuid4()), db=MagicMock(),
                _policy_cache=_cache(),
            )
        # marker consumed even on the raise path so a retry doesn't loop
        assert "__approval_guard_pre_brain_1" not in state

    def test_no_marker_falls_through_to_normal_evaluation(self):
        # No approval marker → the resume-check must fall through. With an
        # empty policy list the normal path returns status='passed'.
        block = {"id": "guard_pre_brain_1"}
        state = {"other": "unrelated"}
        result = _execute_guard(
            block, state, workspace_id=str(uuid.uuid4()), db=MagicMock(),
            _policy_cache=_cache(),
        )
        assert result["status"] == "passed"
        assert result["violations"] == 0

    def test_marker_scoped_by_block_id(self):
        # A marker for a DIFFERENT block must not short-circuit this one.
        block = {"id": "guard_pre_output_1"}
        state = {"__approval_guard_pre_brain_1": "approved"}
        result = _execute_guard(
            block, state, workspace_id=str(uuid.uuid4()), db=MagicMock(),
            _policy_cache=_cache(),
        )
        assert result["status"] == "passed"
        # untouched marker for the other block stays put
        assert state["__approval_guard_pre_brain_1"] == "approved"

    def test_default_block_id_when_missing(self):
        # Falls back to "guard" if block dict has no id field.
        state = {"__approval_guard": "approved"}
        result = _execute_guard(
            {}, state, workspace_id=str(uuid.uuid4()), db=MagicMock(),
            _policy_cache=_cache(),
        )
        assert result["status"] == "resumed_approved"
        assert result["block_id"] == "guard"
