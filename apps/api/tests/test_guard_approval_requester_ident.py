"""Regression test for the "Requester: unknown" bug in Slack approval cards.

Before the fix, guard_block called create_approval_request without
requester_agent_ident. GuardApprovalRequest.requester_agent_ident landed
as None → dispatch_approval_notifications rendered "Requester: unknown".

Fix propagates run.triggered_by (e.g. "lens:user_...") into the approval
request so the Slack card shows a real actor identity.
"""
from __future__ import annotations

import os
import sys
import uuid
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

from app.runtime.blocks.guard_block import _execute_guard  # noqa: E402
from app.runtime.exceptions import ApprovalRequired  # noqa: E402


def test_guard_block_propagates_run_triggered_by_as_requester_ident():
    ws_id = str(uuid.uuid4())
    run_id = uuid.uuid4()
    triggered_by = f"lens:user_{uuid.uuid4().hex[:24]}"

    # Mock DB: db.query(Run.triggered_by).filter(...).scalar() -> triggered_by
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = triggered_by

    # One approval-action rule matching every input.
    rule = {"id": "test.rule", "action": "approval", "match": {}, "message": "approve please"}
    cache = {
        "workspace_id": ws_id,
        "policies": [rule],
        "enforcement_mode": "block",
    }

    block = {"id": "guard_pre_brain_1", "data": {}}
    state = {"input_text": "hello"}

    with patch("app.modules.guard.approval.create_approval_request") as mock_create, \
         patch("app.modules.guard.approval.dispatch_approval_notifications"):
        mock_req = MagicMock()
        mock_req.id = uuid.uuid4()
        mock_req.timeout_at.isoformat.return_value = "2026-01-01T00:00:00Z"
        mock_create.return_value = mock_req

        # First call must raise ApprovalRequired — that's the pause signal.
        try:
            _execute_guard(
                block, state, workspace_id=ws_id, db=db,
                run_id=run_id, _policy_cache=cache,
            )
        except ApprovalRequired:
            pass
        except Exception:
            # If the rule doesn't match every input by default, the branch
            # never fires — the assert below will fail and surface it.
            pass

        # Assert the propagation happened.
        assert mock_create.called, "create_approval_request was not called — rule matcher may have changed"
        kwargs = mock_create.call_args.kwargs
        assert kwargs.get("requester_agent_ident") == triggered_by, (
            f"expected requester_agent_ident={triggered_by!r}, "
            f"got {kwargs.get('requester_agent_ident')!r}"
        )
