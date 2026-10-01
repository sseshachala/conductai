"""Fixture approvals use a disposable database, not installed hook configuration."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models.guard_fixture_approval import GuardFixtureApproval
from app.models.workspace import Workspace
from app.modules.guard.routers.fixture_approvals import (
    ApprovalIn,
    FingerprintIn,
    approve_fixture,
    consume_fixture,
    list_fixtures,
    revoke_fixture,
    router,
)


@pytest.fixture
def database():
    url = os.environ.get("DATABASE_URL", "")
    if not url or "test" not in (make_url(url).database or ""):
        pytest.skip("Requires a dedicated test database")
    engine = create_engine(url, connect_args={"connect_timeout": 2})
    try:
        connection = engine.connect()
    except Exception:
        engine.dispose()
        pytest.skip("Test Postgres is not reachable")
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    workspace = Workspace(name="Fixture review test", owner_id="fixture-owner")
    db.add(workspace)
    db.flush()
    try:
        yield db, str(workspace.id)
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def seed_member(db, ws):
    db.execute(
        text(
            "INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at) VALUES (:ws, 'fixture-subject', 'developer', now())"
        ),
        {"ws": ws},
    )
    db.commit()


def approve(db, ws, digest="a" * 64):
    return approve_fixture(
        ApprovalIn(
            action_digest=digest,
            subject_id="fixture-subject",
            reason="Reviewed synthetic fixture",
            synthetic_reviewed=True,
        ),
        ws,
        "fixture-reviewer",
        "admin",
        db,
    )


def test_single_use_approval_and_audit(database):
    db, ws = database
    seed_member(db, ws)
    approval = approve(db, ws)
    body = FingerprintIn(action_digest="a" * 64)
    result = consume_fixture(body, ws, "fixture-subject", "developer", db)
    assert result["approved"] is True
    assert result["id"] == approval["id"]
    assert consume_fixture(body, ws, "fixture-subject", "developer", db) == {
        "approved": False
    }
    actions = (
        db.execute(
            text("SELECT action FROM audit_log WHERE resource_id = :id"),
            {"id": approval["id"]},
        )
        .scalars()
        .all()
    )
    assert sorted(actions) == ["guard.fixture.approved", "guard.fixture.consumed"]


@pytest.mark.parametrize(
    "mismatch", ["subject", "workspace", "digest", "expired", "revoked"]
)
def test_mismatch_expiry_and_revocation_leave_block_intact(database, mismatch):
    db, ws = database
    seed_member(db, ws)
    approval = approve(db, ws)
    if mismatch == "expired":
        row = db.get(GuardFixtureApproval, UUID(approval["id"]))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    if mismatch == "revoked":
        revoke_fixture(UUID(approval["id"]), ws, "fixture-reviewer", "admin", db)
    body = FingerprintIn(action_digest=("b" if mismatch == "digest" else "a") * 64)
    assert consume_fixture(
        body,
        str(uuid4()) if mismatch == "workspace" else ws,
        "other-subject" if mismatch == "subject" else "fixture-subject",
        "developer",
        db,
    ) == {"approved": False}
    assert db.get(GuardFixtureApproval, UUID(approval["id"])).consumed_at is None


def test_approval_requires_peer_and_existing_member(database):
    db, ws = database
    body = ApprovalIn(
        action_digest="a" * 64,
        subject_id="same-user",
        reason="Synthetic fixture",
        synthetic_reviewed=True,
    )
    with pytest.raises(HTTPException) as exc:
        approve_fixture(body, ws, "same-user", "admin", db)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        approve_fixture(body, ws, "reviewer", "admin", db)
    assert exc.value.status_code == 404


def test_wrong_workspace_cannot_list_or_revoke(database):
    db, ws = database
    seed_member(db, ws)
    approval = approve(db, ws)
    other = str(uuid4())
    assert list_fixtures(other, "admin", db) == []
    with pytest.raises(HTTPException) as exc:
        revoke_fixture(UUID(approval["id"]), other, "reviewer", "admin", db)
    assert exc.value.status_code == 404


@pytest.mark.parametrize("role", ["viewer", "developer", "security", "admin"])
def test_http_approval_admin_only(database, real_require_permission, role):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.core import auth
    from app.core.database import get_db

    db, ws = database
    seed_member(db, ws)
    db.execute(
        text(
            "INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at) VALUES (:ws, 'fixture-reviewer', :role, now())"
        ),
        {"ws": ws, "role": role},
    )
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[auth.get_user_id] = lambda: "fixture-reviewer"
    app.dependency_overrides[auth.get_workspace_id] = lambda: ws
    app.dependency_overrides[get_db] = lambda: db
    for route in router.routes:
        for dep in route.dependant.dependencies:
            permission = getattr(dep.call, "__conduct_permission__", None)
            if permission:
                app.dependency_overrides[dep.call] = auth.require_permission(permission)
    response = TestClient(app).post(
        "/guard/fixture-approvals",
        json={
            "action_digest": "a" * 64,
            "subject_id": "fixture-subject",
            "reason": "Reviewed",
            "synthetic_reviewed": True,
        },
    )
    assert response.status_code == (201 if role == "admin" else 403)


def test_validation_does_not_allow_other_rules_or_implicit_confirmation():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FingerprintIn(action_digest="a" * 64, rule_id="another-rule")
    for confirmation in [False, None]:
        with pytest.raises(ValidationError):
            ApprovalIn(
                action_digest="a" * 64,
                subject_id="member",
                reason="reviewed",
                synthetic_reviewed=confirmation,
            )
