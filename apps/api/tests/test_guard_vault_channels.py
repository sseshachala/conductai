"""Vault-backed notification channels (PagerDuty / webhook / email).

Channels reference a Vault entry through ``integration_id``; credentials are
resolved at send time. DB-backed tests need a dedicated ``*test*`` Postgres.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.crypto import encrypt
from app.models.environment import Environment
from app.models.integration import Integration
from app.models.workspace import Workspace
from app.modules.guard import channel_creds as cc
from app.modules.guard.models import GuardNotificationChannel
from app.modules.guard.routers import alerts as alerts_router
from app.modules.guard.routers import events_notify as en
from app.modules.guard.routers import notifications as notif

PD_KEY = "a" * 32
PD_KEY_ROTATED = "b" * 32
LEGACY_PD_KEY = "c" * 32
URL = "https://93.184.216.34/hook"


@pytest.fixture
def database():
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
    ws = Workspace(name="vault channels", owner_id="fixture-owner")
    db.add(ws)
    db.flush()
    try:
        yield db, ws.id
    finally:
        db.close()
        transaction.rollback()
        conn.close()
        engine.dispose()


def _env(db, ws, name="Production"):
    e = Environment(workspace_id=ws, name=name)
    db.add(e)
    db.flush()
    return e


def _vault(db, ws, env, service, creds, handle=None):
    row = Integration(
        workspace_id=ws, service=service, auth_method="api_key",
        handle=handle or service, encrypted_credentials=encrypt(creds), environment_id=env.id,
    )
    db.add(row)
    db.flush()
    return row


def _channel(db, ws, ctype, ref="", integ=None, action="block"):
    ch = GuardNotificationChannel(
        workspace_id=ws, action=action, channel_type=ctype, channel_ref=ref,
        integration_id=integ.id if integ else None, enabled=True,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture
def posted(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        return MagicMock(status_code=202)

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


# ── PagerDuty ────────────────────────────────────────────────────────────────

def test_pagerduty_resolves_vault_key_and_picks_up_rotation(database, posted):
    db, ws = database
    integ = _vault(db, ws, _env(db, ws), "pagerduty", {"routing_key": PD_KEY})
    ch = _channel(db, ws, "pagerduty", "vault:pagerduty", integ)

    en._fanout_pagerduty([ch], "block", "r1", "msg", db=db, workspace_id=ws)
    assert posted[0][1]["json"]["routing_key"] == PD_KEY

    integ.encrypted_credentials = encrypt({"routing_key": PD_KEY_ROTATED})
    db.flush()
    en._fanout_pagerduty([ch], "block", "r1", "msg", db=db, workspace_id=ws)
    assert posted[1][1]["json"]["routing_key"] == PD_KEY_ROTATED


def test_pagerduty_resolves_without_threading_db(database, posted):
    """Callers that do not pass db still resolve via the row's own session."""
    db, ws = database
    integ = _vault(db, ws, _env(db, ws), "pagerduty", {"routing_key": PD_KEY})
    ch = _channel(db, ws, "pagerduty", "vault:pagerduty", integ)
    en._fanout_pagerduty([ch], "block", "r1", "msg")
    assert posted[0][1]["json"]["routing_key"] == PD_KEY


def test_pagerduty_legacy_raw_ref_still_delivers(database, posted):
    db, ws = database
    ch = _channel(db, ws, "pagerduty", LEGACY_PD_KEY)
    en._fanout_pagerduty([ch], "block", "r1", "msg", db=db, workspace_id=ws)
    assert posted[0][1]["json"]["routing_key"] == LEGACY_PD_KEY


def test_pagerduty_dangling_vault_ref_is_skipped_not_leaked(database, posted):
    db, ws = database
    integ = _vault(db, ws, _env(db, ws), "pagerduty", {"routing_key": PD_KEY})
    ch = _channel(db, ws, "pagerduty", "vault:pagerduty", integ)
    db.delete(integ)
    db.flush()
    en._fanout_pagerduty([ch], "block", "r1", "msg", db=db, workspace_id=ws)
    assert posted == []


def test_vault_entry_of_wrong_service_or_workspace_is_not_used(database, posted):
    db, ws = database
    other = Workspace(name="other", owner_id="o")
    db.add(other)
    db.flush()
    foreign = _vault(db, other.id, _env(db, other.id), "pagerduty", {"routing_key": PD_KEY})
    wrong_service = _vault(db, ws, _env(db, ws), "linear", {"routing_key": PD_KEY}, handle="linear")
    for integ in (foreign, wrong_service):
        ch = _channel(db, ws, "pagerduty", "vault:x", integ)
        en._fanout_pagerduty([ch], "block", "r1", "msg", db=db, workspace_id=ws)
    assert posted == []


# ── Webhook ──────────────────────────────────────────────────────────────────

def test_webhook_signature_header_over_ts_dot_body(database, posted):
    db, ws = database
    integ = _vault(db, ws, _env(db, ws), "webhook", {"url": URL, "signing_secret": "s3cret"})
    ch = _channel(db, ws, "webhook", "vault:webhook", integ)

    en._fanout_webhook([ch], {"event": "x", "n": 1}, db=db, workspace_id=ws)

    url, kw = posted[0]
    assert url == URL
    header = kw["headers"][cc.SIGNATURE_HEADER]
    parts = dict(p.split("=", 1) for p in header.split(","))
    expected = hmac.new(b"s3cret", parts["t"].encode() + b"." + kw["content"], hashlib.sha256).hexdigest()
    assert parts["v1"] == expected
    assert kw["follow_redirects"] is False


def test_webhook_without_signing_secret_sends_no_signature(database, posted):
    db, ws = database
    integ = _vault(db, ws, _env(db, ws), "webhook", {"url": URL})
    ch = _channel(db, ws, "webhook", "vault:webhook", integ)
    en._fanout_webhook([ch], {"event": "x"}, db=db, workspace_id=ws)
    assert "headers" not in posted[0][1] or cc.SIGNATURE_HEADER not in posted[0][1]["headers"]


def test_webhook_rotation_changes_url_and_secret(database, posted):
    db, ws = database
    integ = _vault(db, ws, _env(db, ws), "webhook", {"url": URL})
    ch = _channel(db, ws, "webhook", "vault:webhook", integ)
    integ.encrypted_credentials = encrypt({"url": "https://93.184.216.35/new", "signing_secret": "k"})
    db.flush()
    en._fanout_webhook([ch], {"event": "x"}, db=db, workspace_id=ws)
    assert posted[0][0] == "https://93.184.216.35/new"
    assert cc.SIGNATURE_HEADER in posted[0][1]["headers"]


def test_webhook_legacy_raw_url_still_delivers_unsigned(database, posted):
    db, ws = database
    ch = _channel(db, ws, "webhook", URL)
    en._fanout_webhook([ch], {"event": "x"}, db=db, workspace_id=ws)
    assert posted[0][0] == URL


def test_webhook_send_refuses_private_vault_url(database, posted):
    db, ws = database
    integ = _vault(db, ws, _env(db, ws), "webhook", {"url": "https://169.254.169.254/x", "signing_secret": "k"})
    ch = _channel(db, ws, "webhook", "vault:webhook", integ)
    en._fanout_webhook([ch], {"event": "x"}, db=db, workspace_id=ws)
    assert posted == []


def test_save_refuses_private_vault_webhook_url(database):
    db, ws = database
    integ = _vault(db, ws, _env(db, ws), "webhook", {"url": "https://127.0.0.1/x"})
    with pytest.raises(HTTPException) as exc:
        cc.prepare_channel_ref(db, ws, "webhook", integ.id, "")
    assert exc.value.status_code == 422


def test_vault_save_refuses_private_webhook_url(database, real_require_permission):
    from app.routers.credentials_crud import CredentialUpsert, upsert_credential

    db, ws = database
    with pytest.raises(HTTPException) as exc:
        upsert_credential(CredentialUpsert(service="webhook", handle="webhook",
                                           credentials={"url": "https://10.0.0.5/x"}), db, str(ws), "admin")
    assert exc.value.status_code == 422


# ── Email ────────────────────────────────────────────────────────────────────

def test_email_channel_sends_with_its_environment_credential(database, monkeypatch):
    db, ws = database
    monkeypatch.setenv("RESEND_API_KEY", "")
    prod = _vault(db, ws, _env(db, ws, "Production"), "email", {"resend_api_key": "re_prod", "from_email": "p@x.io"})
    _vault(db, ws, _env(db, ws, "Default"), "email", {"resend_api_key": "re_default"}, handle="email-default")
    sent = []
    monkeypatch.setattr("app.core.email._send_via_resend",
                        lambda key, frm, to, subj, html: sent.append((key, frm, to)) or True)
    ch = _channel(db, ws, "email", "ops@example.com", prod)
    en._fanout_email(db, ws, [ch], "s", "<p>h</p>")
    assert sent == [("re_prod", "Conduct AI <p@x.io>", "ops@example.com")]


def test_email_channel_without_integration_uses_workspace_credential(database, monkeypatch):
    db, ws = database
    sent = []
    monkeypatch.setattr("app.core.email._send_via_resend", lambda key, *a: sent.append(key) or True)
    monkeypatch.setattr("app.core.email._workspace_credential",
                        lambda w, d: SimpleNamespace(resend_api_key="re_ws", sendgrid_api_key=None,
                                                     from_name="N", from_email="n@x.io"))
    ch = _channel(db, ws, "email", "ops@example.com")
    en._fanout_email(db, ws, [ch], "s", "<p>h</p>")
    assert sent == ["re_ws"]


# ── API shaping / validation ─────────────────────────────────────────────────

def test_create_and_list_never_return_vault_or_legacy_secrets(database):
    db, ws = database
    env = _env(db, ws)
    pd = _vault(db, ws, env, "pagerduty", {"routing_key": PD_KEY})
    wh = _vault(db, ws, env, "webhook", {"url": URL + "?token=SECRETTOKEN", "signing_secret": "s3cret"})
    _channel(db, ws, "pagerduty", LEGACY_PD_KEY, action="warn")
    _channel(db, ws, "webhook", URL + "?token=LEGACYTOKEN", action="warn")

    out_pd = notif.create_channel(notif.ChannelCreate(action="block", channel_type="pagerduty",
                                                      integration_id=str(pd.id)), str(ws), db, "admin")
    out_wh = notif.create_channel(notif.ChannelCreate(action="block", channel_type="webhook",
                                                      integration_id=str(wh.id)), str(ws), db, "admin")
    listed = notif.list_channels(str(ws), db, "admin")

    blob = out_pd.model_dump_json() + out_wh.model_dump_json() + listed.model_dump_json()
    for secret in (PD_KEY, LEGACY_PD_KEY, "SECRETTOKEN", "LEGACYTOKEN", "s3cret"):
        assert secret not in blob
    assert out_pd.vault_handle == "pagerduty" and out_pd.environment_name == "Production"
    assert out_pd.legacy_ref is False and out_pd.channel_ref == "vault:pagerduty"
    warn = next(g for g in listed.groups if g.action == "warn").channels
    assert all(c.legacy_ref for c in warn)


def test_create_requires_matching_service_entry(database):
    db, ws = database
    linear = _vault(db, ws, _env(db, ws), "linear", {"api_key": "k"})
    with pytest.raises(HTTPException) as exc:
        notif.create_channel(notif.ChannelCreate(action="block", channel_type="pagerduty",
                                                 integration_id=str(linear.id)), str(ws), db, "admin")
    assert exc.value.status_code == 422


def test_create_pagerduty_without_entry_or_ref_is_422(database):
    db, ws = database
    with pytest.raises(HTTPException) as exc:
        notif.create_channel(notif.ChannelCreate(action="block", channel_type="pagerduty"), str(ws), db, "admin")
    assert exc.value.status_code == 422


def test_email_channel_keeps_recipient_ref_and_validates_entry(database):
    db, ws = database
    email = _vault(db, ws, _env(db, ws), "email", {"resend_api_key": "re"})
    out = notif.create_channel(notif.ChannelCreate(action="warn", channel_type="email",
                                                   integration_id=str(email.id),
                                                   channel_ref="ops@example.com"), str(ws), db, "admin")
    assert out.channel_ref == "ops@example.com" and out.vault_handle == "email"


def test_alerts_create_and_list_use_vault(database):
    db, ws = database
    pd = _vault(db, ws, _env(db, ws), "pagerduty", {"routing_key": PD_KEY})
    out = alerts_router.create_alert(
        alerts_router.AlertCreate(source_type="audit_feed", event_type="collector_stale",
                                  channel_type="pagerduty", integration_id=str(pd.id)),
        str(ws), db, "admin")
    assert out.vault_handle == "pagerduty" and PD_KEY not in out.model_dump_json()
    listed = alerts_router.list_alerts(None, None, str(ws), db, "admin")
    assert PD_KEY not in listed.model_dump_json()


def test_patch_cannot_overwrite_vault_label_with_typed_secret(database):
    db, ws = database
    pd = _vault(db, ws, _env(db, ws), "pagerduty", {"routing_key": PD_KEY})
    out = notif.create_channel(notif.ChannelCreate(action="block", channel_type="pagerduty",
                                                   integration_id=str(pd.id)), str(ws), db, "admin")
    patched = notif.update_channel(out.id, notif.ChannelPatch(channel_ref=LEGACY_PD_KEY), str(ws), db, "admin")
    assert patched.channel_ref == "vault:pagerduty"


def test_vault_list_endpoint_returns_no_credentials(database):
    from app.routers.credentials_integrations import list_channel_vault_entries

    db, ws = database
    _vault(db, ws, _env(db, ws), "webhook", {"url": URL, "signing_secret": "s3cret"})
    out = list_channel_vault_entries("webhook", db, str(ws), "admin")
    assert [e.service for e in out] == ["webhook"]
    assert "s3cret" not in out[0].model_dump_json() and URL not in out[0].model_dump_json()
    with pytest.raises(HTTPException):
        list_channel_vault_entries("github", db, str(ws), "admin")


# ── Pure helpers ─────────────────────────────────────────────────────────────

def test_pagerduty_key_shape():
    assert cc.pagerduty_key_shape_ok(PD_KEY)
    assert not cc.pagerduty_key_shape_ok("short")
    assert not cc.pagerduty_key_shape_ok("")


def test_sign_webhook_body_format():
    header = cc.sign_webhook_body("k", b'{"a":1}', ts=1700000000)
    mac = hmac.new(b"k", b'1700000000.{"a":1}', hashlib.sha256).hexdigest()
    assert header == f"t=1700000000,v1={mac}"


def test_test_switch_pagerduty_and_webhook_send_nothing(posted):
    from app.routers.credentials import CredentialTestRequest, test_credential

    def run(svc, creds):
        return test_credential(CredentialTestRequest(service=svc, credentials=creds), "ws", "admin")

    assert run("pagerduty", {"routing_key": PD_KEY}) == {"ok": True}
    assert run("pagerduty", {"routing_key": "bad"})["ok"] is False
    assert run("webhook", {"url": URL}) == {"ok": True}
    assert run("webhook", {"url": "https://169.254.169.254/x"})["ok"] is False
    assert posted == []


def test_endpoints_declare_permissions():
    from tests.test_endpoint_matrix import ROUTES

    def perms(method, suffix):
        return [r["permissions"] for r in ROUTES if r["method"] == method and r["path"].endswith(suffix)]

    assert {"guard.settings.edit"} in perms("GET", "/credentials/integrations/vault")
    for method, suffix in (("POST", "/guard/notifications"), ("PATCH", "/guard/notifications/{notif_id}"),
                           ("POST", "/guard/alerts"), ("PATCH", "/guard/alerts/{alert_id}")):
        assert {"guard.settings.edit"} in perms(method, suffix), (method, suffix)
    assert {"platform.credentials.manage"} in perms("POST", "/credentials")
    assert {"platform.credentials.manage"} in perms("POST", "/credentials/test")


def test_serialize_masks_legacy_without_db():
    row = SimpleNamespace(channel_type="pagerduty", channel_ref=LEGACY_PD_KEY, integration_id=None)
    assert LEGACY_PD_KEY not in cc.serialize_extras(row, {})["channel_ref"]
    row = SimpleNamespace(channel_type="webhook", channel_ref=URL + "?t=abc", integration_id=None)
    assert cc.serialize_extras(row, {})["channel_ref"] == "https://93.184.216.34/…"
    assert uuid4()  # keep import used
