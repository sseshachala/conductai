"""#4 — audit finalization end-to-end for /gateway/v1/completions (#2144).

Fires a real request through the v2 executor and asserts the resulting
``guard_audit_events`` row carries the fields the Flight Recorder + spend
dashboards + parity tooling all depend on:

- ``route`` == /gateway/v1/completions  (distinguishes canonical from SDK-shaped)
- ``routing_meta.v2_operation`` == openai_chat_completions
- ``routing_meta.revision_id`` == the pinned revision
- ``agent_identity_id`` populated  (#1959 Phase 0 attribution)
- ``decision`` == allowed
- ``execution_status`` == success

FastAPI TestClient drains background tasks before returning, so no manual
audit-drain plumbing is needed here — that's the audit-async gotcha the
reviewer flagged, and it's already handled by the framework in sync mode.
"""
from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient
from sqlalchemy import text


def _query_gateway_audit_row(db, workspace_id: str) -> dict | None:
    """Return the single gateway audit row for this workspace, or None."""
    row = db.execute(
        text("""
            SELECT id::text, workspace_id::text, source, provider, model,
                   decision, execution_status, route, routing_meta,
                   agent_identity_id::text, ai_tool
            FROM guard_audit_events
            WHERE workspace_id = CAST(:ws AS uuid)
            ORDER BY ts DESC
            LIMIT 1
        """),
        {"ws": workspace_id},
    ).fetchone()
    if row is None:
        return None
    routing = row.routing_meta
    if isinstance(routing, str):
        routing = json.loads(routing)
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "source": row.source,
        "provider": row.provider,
        "model": row.model,
        "decision": row.decision,
        "execution_status": row.execution_status,
        "route": row.route,
        "routing_meta": routing or {},
        "agent_identity_id": row.agent_identity_id,
        "ai_tool": row.ai_tool,
    }


def test_completions_writes_audit_row_with_correct_route_operation_revision(
    seeded_profile, gateway_app, it_db,
) -> None:
    client = TestClient(gateway_app)

    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": f"Bearer {seeded_profile['agent_token']}"},
        json={
            "profile": seeded_profile["profile_identifier"],
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        },
    )
    assert resp.status_code == 200, resp.text

    # The audit write is a BackgroundTask. TestClient drains background
    # tasks before returning from client.post() in synchronous mode, so
    # the row should be present immediately. If a future FastAPI/starlette
    # change breaks that guarantee, bump this budget rather than adding
    # a sleep loop — a real regression should surface here, not be masked.
    deadline = time.monotonic() + 5.0
    audit_row: dict | None = None
    while time.monotonic() < deadline:
        audit_row = _query_gateway_audit_row(it_db, seeded_profile["workspace_id"])
        if audit_row is not None:
            break
        it_db.expire_all()
        time.sleep(0.05)
    assert audit_row is not None, (
        "guard_audit_events row never landed after /completions call — "
        "BackgroundTask drain is broken or audit path silently swallowed the write"
    )

    assert audit_row["route"] == "/gateway/v1/completions", audit_row
    assert audit_row["source"] == "gateway", audit_row
    assert audit_row["decision"] == "allowed", audit_row
    # v2 finalize writes execution_status='ok' for happy-path (v1 uses
    # 'success'). PR #2141 landing will unify these — until then the
    # gateway parity contract is that BOTH values indicate a healthy call.
    assert audit_row["execution_status"] in {"ok", "success"}, audit_row
    assert audit_row["agent_identity_id"] == seeded_profile["agent_identity_id"], (
        "#1959 Phase 0 — every /gateway/v1/* audit row must carry the "
        "resolved agent_identity_id for attribution parity"
    )

    routing = audit_row["routing_meta"]
    assert routing.get("v2_operation") == "openai_chat_completions", routing
    assert routing.get("revision_id") == seeded_profile["revision_id"], (
        "revision_id in audit must equal the profile's pinned revision — "
        "otherwise concurrent publish could have switched under the client "
        "mid-request (which the v2 contract forbids)"
    )
