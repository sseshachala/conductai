"""#1712 Track 1 quick win 2/3 — block responses carry a receipt deep-link.

Locks in these properties:
  1. `_render_block` embeds `receipt_id` + `receipt_url` in the 403 payload
  2. Trial callers get a `/b/{id}/{token}` URL; workspace callers get `/theguard/blocks/{id}`
  3. `guarded_completion` BLOCK branch mirrors the same shape via fail_closed(extra=)
  4. `hash_share_token` round-trips (mint → hash → verify)
  5. The receipt URL builder honors CONDUCT_WEB_URL when set
  6. `error.message` embeds the receipt URL for zero-integration SDK surfacing
  7. `guarded_client_call` threads hook_session_id into the audit row
  8. HTTP endpoints — workspace read, cross-workspace 404, public trial read, bad token 404
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid as _uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse


def _fake_rule_decision():
    return SimpleNamespace(
        source="rule",
        rule_id="R-pii-leak",
        reason="Blocked by test rule",
        matched_rules=[{"id": "R-pii-leak", "severity": "block"}],
        defense_score=99,
        inject_guidance=False,
        guidance=None,
        extras={},
    )


def _payload(resp: JSONResponse) -> dict:
    return json.loads(resp.body.decode())


def test_render_block_returns_receipt_id_and_url_workspace_path():
    from app.modules.guard.routers._proxy_helpers import render_block

    bt = BackgroundTasks()
    resp = render_block(
        _fake_rule_decision(), bt,
        workspace_id="00000000-0000-0000-0000-000000000001",
        clerk_user_id="user_test", ai_tool="cursor",
        provider="anthropic", model="claude-sonnet-4-5",
        body={"messages": [{"role": "user", "content": "hi"}]},
        prompt_summary="hi", user_email=None,
        run_id=None, workflow=None, workflow_id=None, hook_session_id=None,
        started=0.0, record_audit_fn=lambda *a, **kw: None,
        fail_closed_fn=lambda s, m, **kw: JSONResponse(status_code=s, content={"error": {"message": m}}),
        is_trial=False,
    )

    body = _payload(resp)
    err = body["error"]
    assert err["type"] == "guard_block"
    assert "receipt_id" in err and err["receipt_id"]
    # Workspace URL never contains the share-token segment
    assert err["receipt_url"].endswith(f"/theguard/blocks/{err['receipt_id']}")
    # Audit was scheduled with pre-minted receipt_id, no share_token_hash for non-trial
    assert bt.tasks, "background audit task must be scheduled"
    audit_kwargs = bt.tasks[0].kwargs
    assert audit_kwargs["receipt_id"] == err["receipt_id"]
    assert audit_kwargs["share_token_hash"] is None


def test_render_block_trial_path_returns_public_receipt_url_and_share_hash():
    from app.modules.guard.routers._proxy_helpers import render_block

    bt = BackgroundTasks()
    resp = render_block(
        _fake_rule_decision(), bt,
        workspace_id="00000000-0000-0000-0000-000000000002",
        clerk_user_id="user_trial", ai_tool="cursor",
        provider="anthropic", model="claude-sonnet-4-5",
        body={"messages": []},
        prompt_summary="hi", user_email=None,
        run_id=None, workflow=None, workflow_id=None, hook_session_id=None,
        started=0.0, record_audit_fn=lambda *a, **kw: None,
        fail_closed_fn=lambda s, m, **kw: JSONResponse(status_code=s, content={}),
        is_trial=True,
    )

    err = _payload(resp)["error"]
    # Trial URL shape: /b/{id}/{token}
    parts = err["receipt_url"].rsplit("/", 3)
    assert parts[-3] == "b"
    assert parts[-2] == err["receipt_id"]
    raw_token = parts[-1]
    from app.guard.receipts import SHARE_TOKEN_PREFIX
    assert raw_token.startswith(SHARE_TOKEN_PREFIX)

    # Hash on the audit row matches sha256(raw_token) — anonymous public
    # endpoint uses this to authorize the reader.
    from app.guard.receipts import hash_share_token
    assert bt.tasks, "background audit task must be scheduled"
    assert bt.tasks[0].kwargs["share_token_hash"] == hash_share_token(raw_token)


def test_guarded_completion_block_carries_receipt_metadata():
    from app.guard.gateway import guarded_completion
    from app.guard.policy_types import PolicyAction

    decision = SimpleNamespace(
        action=PolicyAction.BLOCK,
        rule_id="R-block-lens",
        reason="lens block",
        matched_rules=[{"id": "R-block-lens"}],
        defense_score=88,
        inject_guidance=False,
        guidance=None,
    )

    with patch("app.guard.gateway._evaluate_composed", return_value=decision), \
         patch("app.guard.router.upstream") as upstream_mock:
        resp = asyncio.run(guarded_completion(
            workspace_id="00000000-0000-0000-0000-000000000003",
            clerk_user_id="", ai_tool="lens",
            provider="anthropic", model="claude-sonnet-4-5",
            body={"messages": []},
            upstream_url="https://api.anthropic.com",
            upstream_path="/v1/messages",
            real_key="sk-test",
            auth_header_out="x-api-key",
            bearer=False, is_stream=False,
            background=BackgroundTasks(),
            is_trial=True,
        ))

    upstream_mock.assert_not_called()
    body = _payload(resp)
    meta = body["error"]["metadata"]
    assert meta["receipt_id"]
    # Trial URL from the gateway path
    assert "/b/" in meta["receipt_url"] and meta["receipt_id"] in meta["receipt_url"]


def test_share_token_hash_round_trip():
    from app.guard.receipts import mint_share_token, hash_share_token

    raw, digest = mint_share_token()
    from app.guard.receipts import SHARE_TOKEN_PREFIX
    assert raw.startswith(SHARE_TOKEN_PREFIX)
    assert digest == hash_share_token(raw)
    # Different mint = different digest
    raw2, digest2 = mint_share_token()
    assert digest != digest2


def test_render_block_embeds_receipt_url_in_error_message():
    """#1712 PR 4 — every SDK that raises on `error.message` should
    surface the receipt URL without per-integration wiring."""
    from app.modules.guard.routers._proxy_helpers import render_block

    resp = render_block(
        _fake_rule_decision(), BackgroundTasks(),
        workspace_id="00000000-0000-0000-0000-000000000005",
        clerk_user_id="user", ai_tool="cursor",
        provider="anthropic", model="claude-sonnet-4-5",
        body={"messages": []}, prompt_summary="hi", user_email=None,
        run_id=None, workflow=None, workflow_id=None, hook_session_id=None,
        started=0.0, record_audit_fn=lambda *a, **kw: None,
        fail_closed_fn=lambda s, m, **kw: JSONResponse(status_code=s, content={}),
        is_trial=False,
    )
    err = _payload(resp)["error"]
    assert "→ Receipt:" in err["message"]
    assert err["receipt_url"] in err["message"]


def test_guarded_client_call_forwards_hook_session_id_to_audit(monkeypatch):
    """#1712 Track 1 quick win 3/3 — Lens-in-process LLM calls now carry
    the Lens chat session id into the audit row so a receipt links back to
    the exact conversation that produced it. Previously the block was
    orphaned (hook_session_id NULL) because guarded_client_call didn't
    accept the field."""
    from app.guard import gateway

    recorded: dict = {}
    def _fake_record(*args, **kwargs):
        recorded["kwargs"] = kwargs

    monkeypatch.setattr(gateway, "_record_audit", _fake_record)

    # Compose a BLOCK decision so record() fires on the block path.
    # guarded_client_call imports evaluate_composed locally, so patch the
    # source module — not the alias inside gateway.
    from app.guard import policy as _policy
    from app.guard.policy_types import PolicyAction
    fake = SimpleNamespace(
        action=PolicyAction.BLOCK,
        rule_id="R-lens-test",
        reason="lens block",
        matched_rules=[{"id": "R-lens-test"}],
        defense_score=42,
    )
    monkeypatch.setattr(_policy, "evaluate_composed", lambda ctx: fake)

    try:
        gateway.guarded_client_call(
            client=SimpleNamespace(),
            workspace_id="00000000-0000-0000-0000-000000000004",
            provider="anthropic",
            model="claude-sonnet-4-5",
            messages=[{"role": "user", "content": "hi"}],
            system="",
            hook_session_id="ses_abc123",
        )
    except gateway.GuardedLLMBlocked:
        pass

    assert recorded["kwargs"]["hook_session_id"] == "ses_abc123"


def test_receipt_url_honors_env_overrides_and_defaults_to_localhost(monkeypatch):
    """Resolution order: CONDUCT_WEB_URL > APP_URL > localhost default."""
    from app.guard.receipts import build_receipt_url, DEFAULT_LOCAL_WEB_URL

    monkeypatch.delenv("CONDUCT_WEB_URL", raising=False)
    monkeypatch.delenv("APP_URL", raising=False)
    assert build_receipt_url("abc").startswith(f"{DEFAULT_LOCAL_WEB_URL}/theguard/blocks/")

    monkeypatch.setenv("APP_URL", "https://example.test")
    assert build_receipt_url("abc").startswith("https://example.test/theguard/blocks/")

    # CONDUCT_WEB_URL wins over APP_URL when both are set
    monkeypatch.setenv("CONDUCT_WEB_URL", "https://staging.example.com")
    url = build_receipt_url("abc", "cond_bkr_xyz")
    assert url == "https://staging.example.com/b/abc/cond_bkr_xyz"


# ─── HTTP endpoint tests ──────────────────────────────────────────────────────
# TestClient smoke tests for GET /guard/blocks/{id} and the public path.
# DB is mocked so we can drive different rows into a single test without
# needing a real Postgres.

def _make_audit_row(workspace_id: str, share_token_hash: str | None = None):
    return SimpleNamespace(
        id=_uuid.uuid4(),
        workspace_id=_uuid.UUID(workspace_id),
        ts=datetime.now(timezone.utc),
        decision="blocked",
        rule_id="R-test",
        rule_message="Test block",
        provider="anthropic",
        model="claude-sonnet-4-5",
        ai_tool="cursor",
        input_summary="test input",
        evaluated_rules=[{"id": "R-test"}],
        defense_score=42,
        conductai_run_id=None,
        hook_session_id=None,
        share_token_hash=share_token_hash,
    )


def _client_with_db(db, *, workspace_id: str):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import get_workspace_id, get_user_id

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_workspace_id] = lambda: workspace_id
    app.dependency_overrides[get_user_id] = lambda: "user_test"
    return TestClient(app, raise_server_exceptions=False)


def _clear_overrides():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import get_workspace_id, get_user_id
    for dep in (get_db, get_workspace_id, get_user_id):
        app.dependency_overrides.pop(dep, None)


def test_endpoint_workspace_receipt_returns_row_for_own_workspace():
    ws = "00000000-0000-0000-0000-000000000010"
    row = _make_audit_row(ws)
    db = MagicMock()
    exec_result = MagicMock()
    exec_result.fetchone.return_value = row
    db.execute.return_value = exec_result

    client = _client_with_db(db, workspace_id=ws)
    try:
        resp = client.get(f"/guard/blocks/{row.id}")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["receipt_id"] == str(row.id)
        assert payload["rule_id"] == "R-test"
    finally:
        _clear_overrides()


def test_endpoint_workspace_receipt_404s_across_workspaces():
    row_ws = "00000000-0000-0000-0000-000000000011"
    caller_ws = "00000000-0000-0000-0000-000000000012"
    row = _make_audit_row(row_ws)
    db = MagicMock()
    exec_result = MagicMock()
    exec_result.fetchone.return_value = row
    db.execute.return_value = exec_result

    client = _client_with_db(db, workspace_id=caller_ws)
    try:
        resp = client.get(f"/guard/blocks/{row.id}")
        assert resp.status_code == 404
    finally:
        _clear_overrides()


def test_endpoint_public_receipt_returns_row_with_valid_token_on_trial_workspace():
    from app.guard.receipts import mint_share_token
    ws = "00000000-0000-0000-0000-000000000013"
    raw_token, share_hash = mint_share_token()
    row = _make_audit_row(ws, share_token_hash=share_hash)

    # Two calls: fetchone for the audit row, scalar for the workspace plan.
    db = MagicMock()
    fetch = MagicMock(); fetch.fetchone.return_value = row
    scalar = MagicMock(); scalar.scalar.return_value = "free_trial"
    db.execute.side_effect = [fetch, scalar]

    client = _client_with_db(db, workspace_id="does-not-matter-public-route")
    try:
        resp = client.get(f"/guard/blocks/public/{row.id}/{raw_token}")
        assert resp.status_code == 200
        assert resp.json()["receipt_id"] == str(row.id)
    finally:
        _clear_overrides()


def test_endpoint_public_receipt_404s_on_bad_token_and_non_trial_plan():
    from app.guard.receipts import mint_share_token
    ws = "00000000-0000-0000-0000-000000000014"
    _, share_hash = mint_share_token()
    row = _make_audit_row(ws, share_token_hash=share_hash)

    # Bad token — first call returns the row, we never reach the plan call
    db_bad = MagicMock()
    fetch_bad = MagicMock(); fetch_bad.fetchone.return_value = row
    db_bad.execute.return_value = fetch_bad
    client = _client_with_db(db_bad, workspace_id="x")
    try:
        resp = client.get(f"/guard/blocks/public/{row.id}/cond_bkr_WRONG")
        assert resp.status_code == 404
    finally:
        _clear_overrides()

    # Correct token but workspace has converted to paid — plan gate blocks.
    raw_token, share_hash2 = mint_share_token()
    row2 = _make_audit_row(ws, share_token_hash=share_hash2)
    db_paid = MagicMock()
    fetch2 = MagicMock(); fetch2.fetchone.return_value = row2
    scalar2 = MagicMock(); scalar2.scalar.return_value = "pro"
    db_paid.execute.side_effect = [fetch2, scalar2]
    client = _client_with_db(db_paid, workspace_id="x")
    try:
        resp = client.get(f"/guard/blocks/public/{row2.id}/{raw_token}")
        assert resp.status_code == 404
    finally:
        _clear_overrides()


# ─── POST /guard/blocks/{id}/share — make-shareable ─────────────────────────

def test_endpoint_make_shareable_mints_token_and_returns_public_url():
    """Owner-triggered share: mints token, writes hash, returns public URL."""
    ws = "00000000-0000-0000-0000-000000000020"
    row = _make_audit_row(ws, share_token_hash=None)  # not yet shared

    db = MagicMock()
    fetch_result = MagicMock(); fetch_result.fetchone.return_value = row
    update_result = MagicMock()
    # First execute() = SELECT the row; second = UPDATE share_token_hash
    db.execute.side_effect = [fetch_result, update_result]

    client = _client_with_db(db, workspace_id=ws)
    try:
        resp = client.post(f"/guard/blocks/{row.id}/share")
        assert resp.status_code == 200
        body = resp.json()
        assert body["already_shared"] is False
        assert body["receipt_url"].startswith("http")
        # URL shape: {web}/b/{id}/{cond_bkr_...}
        from app.guard.receipts import SHARE_TOKEN_PREFIX
        assert f"/b/{row.id}/{SHARE_TOKEN_PREFIX}" in body["receipt_url"]
    finally:
        _clear_overrides()


def test_endpoint_make_shareable_returns_already_shared_when_hash_present():
    """Idempotent branch — receipt already has a hash, we don't remint."""
    ws = "00000000-0000-0000-0000-000000000021"
    row = _make_audit_row(ws, share_token_hash="deadbeef" * 8)  # already shared

    db = MagicMock()
    fetch_result = MagicMock(); fetch_result.fetchone.return_value = row
    db.execute.return_value = fetch_result

    client = _client_with_db(db, workspace_id=ws)
    try:
        resp = client.post(f"/guard/blocks/{row.id}/share")
        assert resp.status_code == 200
        body = resp.json()
        assert body["already_shared"] is True
        # Owner who lost the URL sees receipt_url=None — they need to
        # revoke + reshare (future PR) to get a fresh raw token
        assert body["receipt_url"] is None
    finally:
        _clear_overrides()


def test_endpoint_make_shareable_404s_across_workspaces():
    row_ws = "00000000-0000-0000-0000-000000000022"
    caller_ws = "00000000-0000-0000-0000-000000000023"
    row = _make_audit_row(row_ws, share_token_hash=None)

    db = MagicMock()
    fetch_result = MagicMock(); fetch_result.fetchone.return_value = row
    db.execute.return_value = fetch_result

    client = _client_with_db(db, workspace_id=caller_ws)
    try:
        resp = client.post(f"/guard/blocks/{row.id}/share")
        assert resp.status_code == 404
    finally:
        _clear_overrides()
