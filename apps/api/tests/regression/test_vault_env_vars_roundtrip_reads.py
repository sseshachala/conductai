"""Vault env-var round-trip regression tests (#2054 Phase 1) — read paths:
get_credential env fallback, metadata-only list, audited reveal.

Split from ``test_vault_env_vars_roundtrip.py``; shared helpers live in
``_vault_env_vars_helpers.py``.
"""
from __future__ import annotations

import uuid

import pytest

from tests.regression.conftest import requires_db
from tests.regression._vault_env_vars_helpers import (
    _cleanup,
    _seed_environment,
    _seed_integration,
)


pytestmark = [requires_db, pytest.mark.usefixtures("local_development_auth")]


# --- 16. get_credential fallback prefers Default env, not arbitrary cross-env ---


def test_get_credential_no_env_prefers_default_over_arbitrary_first_match(
    client, seeded_workspace,
):
    """Reviewer P1-3: previously an arbitrary .first() across every
    environment could return a staging key when a background worker
    (Slack webhook, watchdog, email) asked for a handle without an env.
    Fix: no env supplied → workspace's Default env row wins; only then
    workspace-unscoped rows; never cross-env first-match."""
    from app.core.database import SessionLocal
    from app.core.credentials import get_credential
    from app.models.environment import Environment

    ws_id, _token = seeded_workspace
    # Two named envs; a Default with the correct anthropic row and a
    # staging env with a rotated key that must NEVER surface via the
    # env-less fallback.
    default_env = uuid.uuid4()
    staging_env = uuid.uuid4()
    with SessionLocal() as db:
        db.add(Environment(id=default_env, workspace_id=ws_id, name="Default"))
        db.add(Environment(id=staging_env, workspace_id=ws_id, name="staging"))
        db.commit()

    _seed_integration(ws_id, default_env, "anthropic", {"api_key": "prod-key"})
    _seed_integration(ws_id, staging_env, "anthropic", {"api_key": "staging-key"})
    try:
        with SessionLocal() as db:
            got = get_credential(db, str(ws_id), "anthropic")
            assert got.get("api_key") == "prod-key", (
                "env-less fallback resolved a non-Default environment — "
                "reintroduced the P1-3 cross-env leak."
            )
    finally:
        _cleanup(ws_id, default_env)
        with SessionLocal() as db:
            db.query(Environment).filter(Environment.id == staging_env).delete()
            db.commit()


def test_get_credential_no_env_falls_back_to_workspace_unscoped_row(
    client, seeded_workspace,
):
    """Some legacy tables use env-agnostic rows (proxy_config, etc.). When
    no Default env has a matching row, fall through to a workspace-level
    unscoped row rather than searching other envs."""
    from app.core.database import SessionLocal
    from app.core.credentials import get_credential
    from app.models.environment import Environment
    from app.models.integration import Integration
    from app.core.crypto import encrypt

    ws_id, _token = seeded_workspace
    default_env = uuid.uuid4()
    with SessionLocal() as db:
        db.add(Environment(id=default_env, workspace_id=ws_id, name="Default"))
        # Unscoped (workspace-level) row for the legacy handle.
        db.add(Integration(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            environment_id=None,
            service="proxy_config",
            handle="proxy_config",
            auth_method="api_key",
            encrypted_credentials=encrypt({"LLM_UPSTREAM": "https://prod"}),
            revision=1,
        ))
        db.commit()
    try:
        with SessionLocal() as db:
            got = get_credential(db, str(ws_id), "proxy_config")
            assert got.get("LLM_UPSTREAM") == "https://prod"
    finally:
        _cleanup(ws_id, default_env)


# --- 20. list_env_vars never returns values (Phase 1 finisher) ---


def test_list_env_vars_never_returns_values(client, seeded_workspace):
    """Reviewer P2 (round 1): the environment editor was a mass-reveal
    endpoint dressed up as a list. Now the list carries metadata only —
    values must never appear even for a caller with full permissions."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "anthropic", {"api_key": "sk-secret-anthropic"})
        _seed_integration(ws_id, env_id, "env_vars", {"CUSTOM": "value-should-not-appear"})

        r = client.get(f"/credentials/env-vars/{env_id}?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        body_text = r.text
        assert "sk-secret-anthropic" not in body_text
        assert "value-should-not-appear" not in body_text
        for row in r.json():
            assert "value" not in row
            assert "has_value" in row
    finally:
        _cleanup(ws_id, env_id)


# --- 21. reveal returns one field value and writes an audit row ---


def test_reveal_returns_value_and_writes_audit_event(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "anthropic", {"api_key": "sk-real"})

        # Snapshot audit-log row count before.
        from app.core.database import SessionLocal
        from app.models.audit_log import AuditLog
        with SessionLocal() as db:
            before = db.query(AuditLog).filter(
                AuditLog.workspace_id == ws_id,
                AuditLog.action == "credential.reveal",
            ).count()

        r = client.post(
            f"/credentials/env-vars/{env_id}/reveal?workspace_id={ws_id}",
            json={"handle": "anthropic", "field": "api_key"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"handle": "anthropic", "field": "api_key", "value": "sk-real"}

        with SessionLocal() as db:
            after = db.query(AuditLog).filter(
                AuditLog.workspace_id == ws_id,
                AuditLog.action == "credential.reveal",
            ).count()
        assert after == before + 1, "reveal did not write an audit row"
    finally:
        _cleanup(ws_id, env_id)


# --- 22. reveal audits failed attempts too ---


def test_reveal_audits_failure_when_field_not_present(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "anthropic", {"api_key": "sk-real"})

        from app.core.database import SessionLocal
        from app.models.audit_log import AuditLog
        with SessionLocal() as db:
            before = db.query(AuditLog).filter(
                AuditLog.workspace_id == ws_id,
                AuditLog.action == "credential.reveal",
            ).count()

        r = client.post(
            f"/credentials/env-vars/{env_id}/reveal?workspace_id={ws_id}",
            json={"handle": "anthropic", "field": "no_such_field"},
        )
        assert r.status_code == 404, r.text

        with SessionLocal() as db:
            after = db.query(AuditLog).filter(
                AuditLog.workspace_id == ws_id,
                AuditLog.action == "credential.reveal",
            ).count()
        assert after == before + 1, "failed reveal did not write an audit row"
    finally:
        _cleanup(ws_id, env_id)


# --- 23. reveal refuses cross-workspace env ---


def test_reveal_refuses_cross_workspace_environment(client, seeded_workspace):
    ws_a, _t = seeded_workspace
    env_a = _seed_environment(ws_a)

    from datetime import datetime, timezone
    from app.core.database import SessionLocal
    from app.models.environment import Environment
    from app.models.workspace import Workspace

    ws_b = uuid.uuid4()
    env_b = uuid.uuid4()
    with SessionLocal() as db:
        db.add(Workspace(
            id=ws_b,
            name=f"cross-{ws_b.hex[:8]}",
            owner_id=f"user_test_cross_{ws_b.hex[:8]}",
            plan="free",
            is_approved=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.add(Environment(id=env_b, workspace_id=ws_b, name="rival"))
        db.commit()
    _seed_integration(ws_b, env_b, "anthropic", {"api_key": "sk-other"})
    try:
        r = client.post(
            f"/credentials/env-vars/{env_b}/reveal?workspace_id={ws_a}",
            json={"handle": "anthropic", "field": "api_key"},
        )
        assert r.status_code == 404, r.text
    finally:
        _cleanup(ws_a, env_a)
        with SessionLocal() as db:
            from app.models.integration import Integration
            db.query(Integration).filter(Integration.workspace_id == ws_b).delete()
            db.query(Environment).filter(Environment.id == env_b).delete()
            db.query(Workspace).filter(Workspace.id == ws_b).delete()
            db.commit()


# --- 24. list_env_vars uses snake_case wire keys (client contract) ---


def test_list_env_vars_wire_keys_are_snake_case(client, seeded_workspace):
    """Regression pin: the frontend reads has_value from the wire and
    would silently short-circuit reveal-gating if we ever renamed to
    camelCase. Freezing the wire keys stops that class of bug."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "anthropic", {"api_key": "sk-x"})
        r = client.get(f"/credentials/env-vars/{env_id}?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        row = r.json()[0]
        assert "has_value" in row
        assert "hasValue" not in row
    finally:
        _cleanup(ws_id, env_id)
