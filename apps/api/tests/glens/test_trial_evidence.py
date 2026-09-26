"""Exercise real SQL reads and RBAC; no mocked query chains."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine, text
from sqlalchemy.orm import Session

from app.modules.agent_identity.models import AgentIdentity
from app.modules.glens.trial_evidence import TrialEvidenceQuery, read_trial_evidence
from app.modules.guard.models import GuardAuditEvent

WS = UUID("00000000-0000-0000-0000-000000000001")
OTHER = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)


@pytest.fixture
def data(monkeypatch):
    from app.core import auth
    monkeypatch.setattr(auth, "_clerk_enabled_dispatch", lambda: True)
    engine = create_engine("sqlite://")
    metadata = MetaData()
    def projection(model, names):
        return Table(model.__tablename__, metadata, *[
            Column(name, Uuid(native_uuid=False) if isinstance(model.__table__.c[name].type, Uuid)
                   else model.__table__.c[name].type, primary_key=name == "id") for name in names
        ])
    identities = projection(AgentIdentity, ["id", "workspace_id", "source", "owner_user_id"])
    events = projection(GuardAuditEvent, [
        "id", "workspace_id", "agent_identity_id", "request_id", "ts", "decision",
        "rule_id", "policy_hash", "provider", "model", "lifecycle_state", "execution_status",
    ])
    metadata.create_all(engine)
    with Session(engine) as db:
        for ddl in [
            "CREATE TABLE workspace_users (workspace_id TEXT, clerk_user_id TEXT, role TEXT)",
            "CREATE TABLE roles (id INTEGER, name TEXT, workspace_id TEXT)",
            "CREATE TABLE permissions (id INTEGER, name TEXT)",
            "CREATE TABLE role_permissions (role_id INTEGER, permission_id INTEGER)",
            "INSERT INTO roles VALUES (1, 'developer', NULL), (2, 'admin', NULL), (3, 'viewer', NULL)",
            "INSERT INTO permissions VALUES (1, 'guard.activity.view_own'), (2, 'guard.activity.view_all')",
            "INSERT INTO role_permissions VALUES (1, 1), (2, 1), (2, 2)",
        ]:
            db.execute(text(ddl))
        for user, role in [("alice", "developer"), ("bob", "developer"), ("admin", "admin"), ("viewer", "viewer")]:
            db.execute(text("INSERT INTO workspace_users VALUES (:ws, :uid, :role)"),
                       {"ws": str(WS), "uid": user, "role": role})
        db.execute(identities.insert(), [
            {"id": "alice-trial", "workspace_id": WS, "source": "conduct_trial", "owner_user_id": "alice"},
            {"id": "bob-trial", "workspace_id": WS, "source": "conduct_trial", "owner_user_id": "bob"},
            {"id": "foreign", "workspace_id": OTHER, "source": "conduct_trial", "owner_user_id": "alice"},
            {"id": "normal", "workspace_id": WS, "source": "conduct_auto", "owner_user_id": "alice"},
        ])
        def add(identity="alice-trial", workspace=WS, when=NOW, **changes):
            row = dict(id=uuid4(), workspace_id=workspace, agent_identity_id=identity,
                       request_id=uuid4(), ts=when, decision="allowed", rule_id=None,
                       policy_hash=None, provider="anthropic", model="test-model",
                       lifecycle_state="finalized", execution_status=None)
            row.update(changes)
            db.execute(events.insert().values(**row))
            return row
        yield db, add
    engine.dispose()


def query(**kwargs):
    return TrialEvidenceQuery(since=NOW - timedelta(hours=1), until=NOW + timedelta(hours=1), **kwargs)


def test_own_scope_excludes_other_users_workspaces_and_nontrial(data):
    db, add = data
    own = add()
    add("bob-trial")
    add("foreign", OTHER)
    add("foreign")  # Malformed cross-workspace association must not leak either.
    add("normal")
    result = read_trial_evidence(db, str(WS), "alice", query())
    assert result.status == "ok"
    assert result.total_matching == 1
    assert [r.source_id for r in result.records] == [own["id"]]
    assert result.records[0].execution_status is None
    assert result.records[0].policy_hash is None


@pytest.mark.parametrize("user", ["alice", "viewer", "outsider", None])
def test_workspace_scope_requires_current_authority(data, user):
    db, add = data
    add()
    result = read_trial_evidence(db, str(WS), user, query(scope="workspace"))
    assert result.status == "denied"
    assert result.total_matching is None
    assert result.records == []


def test_admin_workspace_scope_still_excludes_other_workspace(data):
    db, add = data
    add()
    add("bob-trial")
    add("foreign", OTHER)
    result = read_trial_evidence(db, str(WS), "admin", query(scope="workspace"))
    assert result.total_matching == 2


def test_admin_own_scope_is_not_silently_broadened(data):
    db, add = data
    add()
    assert read_trial_evidence(db, str(WS), "admin", query()).status == "empty"


def test_viewer_cannot_read_own_trial_events(data):
    db, _ = data
    assert read_trial_evidence(db, str(WS), "viewer", query()).status == "denied"


def test_limit_reports_exact_total_and_stable_order(data):
    db, add = data
    rows = [add() for _ in range(3)]
    result = read_trial_evidence(db, str(WS), "alice", query(limit=2))
    assert result.status == "partial"
    assert result.total_matching == 3 and result.has_more is True
    assert [r.source_id for r in result.records] == sorted([r["id"] for r in rows], reverse=True)[:2]


def test_request_filter_reports_missing_without_disclosing_ownership(data):
    db, add = data
    own, other = add(), add("bob-trial")
    requested = [own["request_id"], other["request_id"]]
    result = read_trial_evidence(db, str(WS), "alice", query(request_ids=requested))
    assert result.status == "partial" and result.has_more is False
    assert result.total_matching == 1
    foreign_only = read_trial_evidence(db, str(WS), "alice", query(request_ids=[other["request_id"]]))
    missing = read_trial_evidence(db, str(WS), "alice", query(request_ids=[uuid4()]))
    assert foreign_only.status == missing.status == "empty"
    assert foreign_only.limitations == missing.limitations


def test_window_is_half_open(data):
    db, add = data
    add(when=NOW - timedelta(hours=1))
    add(when=NOW + timedelta(hours=1))
    assert read_trial_evidence(db, str(WS), "alice", query()).total_matching == 1


def test_storage_error_is_unavailable_not_zero_or_raw_sql(data):
    db, _ = data
    db.execute(text("DROP TABLE guard_audit_events"))
    result = read_trial_evidence(db, str(WS), "alice", query())
    assert result.status == "unavailable"
    assert result.total_matching is None and result.has_more is None
    assert "SELECT" not in result.model_dump_json()


def test_revoked_membership_is_rechecked(data):
    db, add = data
    add()
    assert read_trial_evidence(db, str(WS), "alice", query()).status == "ok"
    db.execute(text("DELETE FROM workspace_users WHERE clerk_user_id='alice'"))
    assert read_trial_evidence(db, str(WS), "alice", query()).status == "denied"


@pytest.mark.parametrize("arguments", [
    {"since": "2026-09-25T12:00:00"}, {"limit": 0}, {"limit": 101},
    {"limit": True}, {"scope": "org"}, {"request_ids": []},
    {"request_ids": ["not-a-uuid"]}, {"workspace_id": str(OTHER)},
    {"since": NOW, "until": NOW}, {"since": NOW, "until": NOW + timedelta(days=32)},
])
def test_invalid_or_scope_injecting_arguments_rejected(arguments):
    with pytest.raises(ValidationError):
        TrialEvidenceQuery(**arguments)


def test_defaults_and_timezone_normalization():
    default = TrialEvidenceQuery()
    assert default.until - default.since == timedelta(days=1)
    q = TrialEvidenceQuery(since="2026-09-25T07:00:00-05:00", until="2026-09-25T08:00:00-05:00")
    assert q.since == NOW


def test_registered_tool_returns_json_contract_with_no_payload_fields(data, monkeypatch):
    from app.tools.registry import default_registry
    from app.tools.registrations.lens import trial_evidence  # noqa: F401
    db, add = data
    add()
    monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)
    monkeypatch.setattr("app.core.workspace_context.set_workspace_rls", lambda *args: None)
    tool = default_registry.get("get_trial_evidence")
    response = tool.impl(SimpleNamespace(workspace_id=str(WS), clerk_user_id="alice"),
                         since=NOW - timedelta(hours=1), until=NOW + timedelta(hours=1))
    assert response["status"] == "ok"
    assert response["contract_version"] == 2
    assert response["timezone"] == "UTC"
    assert not {"input_summary", "result_summary", "routing_meta", "token_encrypted", "user_email"} & response["records"][0].keys()
    json.dumps(response)


def test_connection_failure_returns_unavailable_without_exception_details(monkeypatch):
    from sqlalchemy.exc import OperationalError
    from app.tools.registrations.lens.trial_evidence import get_trial_evidence
    def fail():
        raise OperationalError("private SQL", {}, Exception("private connection details"))
    monkeypatch.setattr("app.core.database.SessionLocal", fail)
    response = get_trial_evidence(SimpleNamespace(workspace_id=str(WS), clerk_user_id="alice"))
    assert response["status"] == "unavailable"
    assert response["total_matching"] is None
    assert "private" not in json.dumps(response)
