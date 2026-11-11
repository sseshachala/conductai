"""Relink a channel's Vault entry and move a legacy typed key into the Vault.

Endpoints are exercised over HTTP with auth dependencies overridden; the
permission check itself is recorded so both required permissions are asserted.
DB-backed tests need a dedicated ``*test*`` Postgres.
"""
from __future__ import annotations

import logging
import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.environment import Environment
from app.models.integration import Integration
from app.models.workspace import Workspace
from app.modules.guard.models import GuardNotificationChannel
from app.modules.guard.routers import alerts as alerts_router
from app.modules.guard.routers import notifications as notif_router

PD_KEY = "a" * 32
PD_KEY_2 = "b" * 32
URL = "https://93.184.216.34/hook"


@pytest.fixture
def ctx():
    url = os.environ.get("DATABASE_URL", "")
    if not url or "test" not in (make_url(url).database or ""):
        pytest.skip("Requires a dedicated test database")
    engine = create_engine(url, connect_args={"connect_timeout": 2})
    try:
        conn = engine.connect()
    except Exception:
        engine.dispose()
        pytest.skip("Test Postgres is not reachable")
    transaction = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    ws = Workspace(name="relink move", owner_id="fixture-owner")
    other = Workspace(name="other", owner_id="fixture-owner-2")
    db.add_all([ws, other])
    db.flush()

    app = FastAPI()
    app.include_router(notif_router.router)
    app.include_router(alerts_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_workspace_id] = lambda: str(ws.id)
    app.dependency_overrides[get_user_id] = lambda: "user_admin"
    client = TestClient(app)
    try:
        yield type("Ctx", (), {"db": db, "ws": ws.id, "other": other.id, "client": client})
    finally:
        db.close()
        transaction.rollback()
        conn.close()
        engine.dispose()


def _env(c, name="Production", ws=None):
    e = Environment(workspace_id=ws or c.ws, name=name)
    c.db.add(e)
    c.db.flush()
    return e


def _vault(c, env, service, creds, handle=None, ws=None):
    row = Integration(
        workspace_id=ws or c.ws, service=service, auth_method="api_key",
        handle=handle or service, encrypted_credentials=encrypt(creds), environment_id=env.id,
    )
    c.db.add(row)
    c.db.flush()
    return row


def _chan(c, ctype, ref="", integ=None, action="block", source=None, event=None):
    ch = GuardNotificationChannel(
        workspace_id=c.ws, action=action if source is None else "alert", channel_type=ctype,
        channel_ref=ref, integration_id=integ.id if integ else None, enabled=True,
        **({"source_type": source, "event_type": event} if source else {}),
    )
    c.db.add(ch)
    c.db.flush()
    c.db.commit()  # release the savepoint so later request rollbacks keep the fixtures
    return ch


def _q(c):
    return {"workspace_id": str(c.ws)}


# ── Relink ───────────────────────────────────────────────────────────────────

def test_relink_pagerduty_to_other_entry(ctx):
    env = _env(ctx)
    a = _vault(ctx, env, "pagerduty", {"routing_key": PD_KEY}, handle="pd-a")
    b = _vault(ctx, env, "pagerduty", {"routing_key": PD_KEY_2}, handle="pd-b")
    ch = _chan(ctx, "pagerduty", "vault:pd-a", a)
    r = ctx.client.patch(f"/guard/notifications/{ch.id}", params=_q(ctx), json={"integration_id": str(b.id)})
    assert r.status_code == 200, r.text
    assert r.json()["vault_handle"] == "pd-b" and r.json()["integration_id"] == str(b.id)
    ctx.db.refresh(ch)
    assert ch.channel_ref == "vault:pd-b"


def test_relink_email_keeps_recipient(ctx):
    env = _env(ctx)
    e = _vault(ctx, env, "email", {"resend_api_key": "re_x"}, handle="mail")
    ch = _chan(ctx, "email", "ops@example.com")
    r = ctx.client.patch(f"/guard/notifications/{ch.id}", params=_q(ctx), json={"integration_id": str(e.id)})
    assert r.status_code == 200, r.text
    assert r.json()["channel_ref"] == "ops@example.com" and r.json()["vault_handle"] == "mail"


def test_relink_slack_validates_service(ctx):
    env = _env(ctx)
    good = _vault(ctx, env, "slack", {"token": "xoxb-x"}, handle="slk")
    bad = _vault(ctx, env, "pagerduty", {"routing_key": PD_KEY}, handle="pd")
    ch = _chan(ctx, "slack", "alerts")
    r = ctx.client.patch(f"/guard/notifications/{ch.id}", params=_q(ctx), json={"integration_id": str(bad.id)})
    assert r.status_code == 422
    r = ctx.client.patch(f"/guard/notifications/{ch.id}", params=_q(ctx), json={"integration_id": str(good.id)})
    assert r.status_code == 200 and r.json()["vault_handle"] == "slk"


def test_relink_wrong_service_422(ctx):
    env = _env(ctx)
    pd = _vault(ctx, env, "pagerduty", {"routing_key": PD_KEY}, handle="pd")
    hook = _vault(ctx, env, "webhook", {"url": URL}, handle="hook")
    ch = _chan(ctx, "webhook", "vault:hook", hook)
    r = ctx.client.patch(f"/guard/notifications/{ch.id}", params=_q(ctx), json={"integration_id": str(pd.id)})
    assert r.status_code == 422
    ctx.db.refresh(ch)
    assert ch.integration_id == hook.id and ch.channel_ref == "vault:hook"


def test_relink_other_workspace_422(ctx):
    env_other = _env(ctx, ws=ctx.other)
    foreign = _vault(ctx, env_other, "pagerduty", {"routing_key": PD_KEY}, handle="pd", ws=ctx.other)
    env = _env(ctx)
    mine = _vault(ctx, env, "pagerduty", {"routing_key": PD_KEY_2}, handle="pd-mine")
    ch = _chan(ctx, "pagerduty", "vault:pd-mine", mine)
    r = ctx.client.patch(f"/guard/notifications/{ch.id}", params=_q(ctx), json={"integration_id": str(foreign.id)})
    assert r.status_code == 422


def test_relink_webhook_egress_checked(ctx):
    env = _env(ctx)
    ok = _vault(ctx, env, "webhook", {"url": URL}, handle="ok")
    internal = _vault(ctx, env, "webhook", {"url": "http://127.0.0.1/x"}, handle="internal")
    ch = _chan(ctx, "webhook", "vault:ok", ok)
    r = ctx.client.patch(f"/guard/notifications/{ch.id}", params=_q(ctx), json={"integration_id": str(internal.id)})
    assert r.status_code == 422 and "refused" in r.json()["detail"]


def test_relink_alert_row(ctx):
    env = _env(ctx)
    a = _vault(ctx, env, "webhook", {"url": URL}, handle="h1")
    b = _vault(ctx, env, "webhook", {"url": "https://93.184.216.34/other"}, handle="h2")
    ch = _chan(ctx, "webhook", "vault:h1", a, source="gateway", event="blocked")
    r = ctx.client.patch(f"/guard/alerts/{ch.id}", json={"integration_id": str(b.id)})
    assert r.status_code == 200 and r.json()["vault_handle"] == "h2"
    pd = _vault(ctx, env, "pagerduty", {"routing_key": PD_KEY}, handle="pd")
    r = ctx.client.patch(f"/guard/alerts/{ch.id}", json={"integration_id": str(pd.id)})
    assert r.status_code == 422


# ── Move to Vault ────────────────────────────────────────────────────────────

def _move(ctx, ch, env, handle, path="notifications"):
    q = _q(ctx) if path == "notifications" else None
    return ctx.client.post(
        f"/guard/{path}/{ch.id}/move-to-vault", params=q,
        json={"environment_id": str(env.id), "handle": handle},
    )


def test_move_pagerduty_creates_entry_rebinds_and_audits(ctx, caplog):
    env = _env(ctx)
    ch = _chan(ctx, "pagerduty", PD_KEY)
    with caplog.at_level(logging.DEBUG):
        r = _move(ctx, ch, env, "pd-prod")
    assert r.status_code == 200, r.text
    assert PD_KEY not in r.text and PD_KEY not in caplog.text
    body = r.json()
    assert body["vault_handle"] == "pd-prod" and body["legacy_ref"] is False
    assert body["channel_ref"] == "vault:pd-prod" and body["environment_id"] == str(env.id)
    entry = ctx.db.query(Integration).filter_by(workspace_id=ctx.ws, handle="pd-prod").one()
    assert entry.service == "pagerduty" and entry.environment_id == env.id
    assert decrypt(entry.encrypted_credentials) == {"routing_key": PD_KEY}
    ctx.db.refresh(ch)
    assert ch.integration_id == entry.id and ch.channel_ref == "vault:pd-prod"
    audit = ctx.db.query(AuditLog).filter_by(workspace_id=ctx.ws, action="guard.channel.moved_to_vault").one()
    assert audit.actor_id == "user_admin" and audit.resource_id == str(ch.id)
    assert audit.meta["reused_entry"] is False and PD_KEY not in str(audit.meta)


def test_move_webhook_alert_row(ctx):
    env = _env(ctx)
    ch = _chan(ctx, "webhook", URL, source="gateway", event="blocked")
    r = _move(ctx, ch, env, "hook-prod", path="alerts")
    assert r.status_code == 200, r.text
    assert URL not in r.text and r.json()["vault_handle"] == "hook-prod"
    entry = ctx.db.query(Integration).filter_by(workspace_id=ctx.ws, handle="hook-prod").one()
    assert entry.service == "webhook" and decrypt(entry.encrypted_credentials) == {"url": URL}


def test_move_reuses_identical_entry(ctx):
    env = _env(ctx)
    existing = _vault(ctx, env, "pagerduty", {"routing_key": PD_KEY}, handle="already")
    ch = _chan(ctx, "pagerduty", PD_KEY)
    r = _move(ctx, ch, env, "something-else")
    assert r.status_code == 200, r.text
    assert r.json()["vault_handle"] == "already"
    assert ctx.db.query(Integration).filter_by(workspace_id=ctx.ws, service="pagerduty").count() == 1
    ctx.db.refresh(ch)
    assert ch.integration_id == existing.id
    audit = ctx.db.query(AuditLog).filter_by(workspace_id=ctx.ws, action="guard.channel.moved_to_vault").one()
    assert audit.meta["reused_entry"] is True


def test_move_handle_collision_409_and_row_untouched(ctx):
    env = _env(ctx)
    _vault(ctx, env, "pagerduty", {"routing_key": PD_KEY_2}, handle="taken")
    ch = _chan(ctx, "pagerduty", PD_KEY)
    r = _move(ctx, ch, env, "taken")
    assert r.status_code == 409 and PD_KEY not in r.text
    ctx.db.refresh(ch)
    assert ch.integration_id is None and ch.channel_ref == PD_KEY


def test_move_webhook_egress_refused_422(ctx):
    env = _env(ctx)
    ch = _chan(ctx, "webhook", "http://127.0.0.1:8080/hook")
    r = _move(ctx, ch, env, "bad")
    assert r.status_code == 422 and "refused" in r.json()["detail"]
    assert ctx.db.query(Integration).filter_by(workspace_id=ctx.ws, handle="bad").count() == 0
    ctx.db.refresh(ch)
    assert ch.integration_id is None


def test_move_foreign_environment_404(ctx):
    foreign = _env(ctx, ws=ctx.other)
    ch = _chan(ctx, "pagerduty", PD_KEY)
    r = _move(ctx, ch, foreign, "pd")
    assert r.status_code == 404


def test_move_rejects_vault_backed_and_slack_rows(ctx):
    env = _env(ctx)
    entry = _vault(ctx, env, "pagerduty", {"routing_key": PD_KEY}, handle="pd")
    backed = _chan(ctx, "pagerduty", "vault:pd", entry)
    slack = _chan(ctx, "slack", "alerts")
    assert _move(ctx, backed, env, "x").status_code == 409
    assert _move(ctx, slack, env, "x").status_code == 409


def test_move_bad_handle_422(ctx):
    env = _env(ctx)
    ch = _chan(ctx, "pagerduty", PD_KEY)
    assert _move(ctx, ch, env, "has space").status_code == 422


def _declared_permissions(router, path):
    """Permissions declared on a route (conftest tags each require_permission closure)."""
    route = next(r for r in router.routes if r.path == path and "POST" in r.methods)
    return {getattr(d.call, "__conduct_permission__", None) for d in route.dependant.dependencies}


@pytest.mark.parametrize("router,path", [
    (notif_router.router, "/guard/notifications/{notif_id}/move-to-vault"),
    (notif_router.router, "/guard/notifications/move-all-to-vault"),
    (alerts_router.router, "/guard/alerts/{alert_id}/move-to-vault"),
])
def test_move_requires_both_permissions(router, path):
    perms = _declared_permissions(router, path)
    assert {"guard.settings.edit", "platform.credentials.manage"} <= perms


def test_legacy_rows_unaffected_by_other_patches(ctx):
    ch = _chan(ctx, "pagerduty", PD_KEY)
    r = ctx.client.patch(f"/guard/notifications/{ch.id}", params=_q(ctx), json={"enabled": False})
    assert r.status_code == 200 and r.json()["legacy_ref"] is True
    ctx.db.refresh(ch)
    assert ch.channel_ref == PD_KEY and ch.integration_id is None
    listing = ctx.client.get("/guard/notifications", params=_q(ctx))
    assert PD_KEY not in listing.text


# ── Bulk ─────────────────────────────────────────────────────────────────────

def test_move_all_moves_reuses_and_skips_refused(ctx):
    env = _env(ctx)
    a = _chan(ctx, "pagerduty", PD_KEY)
    a2 = _chan(ctx, "pagerduty", PD_KEY, action="warn")  # same key -> shared entry
    h = _chan(ctx, "webhook", URL)
    bad = _chan(ctx, "webhook", "http://127.0.0.1/x")
    r = ctx.client.post("/guard/notifications/move-all-to-vault", params=_q(ctx),
                        json={"environment_id": str(env.id)})
    assert r.status_code == 200, r.text
    out = r.json()
    assert set(out["moved"]) == {str(a.id), str(a2.id), str(h.id)}
    assert [s["id"] for s in out["skipped"]] == [str(bad.id)]
    assert PD_KEY not in r.text and URL not in r.text
    assert ctx.db.query(Integration).filter_by(workspace_id=ctx.ws, service="pagerduty").count() == 1
    ctx.db.refresh(bad)
    assert bad.integration_id is None
    assert ctx.db.query(AuditLog).filter_by(workspace_id=ctx.ws, action="guard.channel.moved_to_vault").count() == 3
