"""Lens evidence journeys on PostgreSQL, with a non-owner role and workflow RLS.

LENS_TEST_DATABASE_URL must point to a disposable PostgreSQL database whose
test owner can create roles. Every test removes its random schema and role.
No production credentials, LLM calls or existing application rows are used.
"""
import importlib.util
import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, MetaData, Table, create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.workspace_context import set_workspace_rls
from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.models.run import Run, RunEvent
from app.models.workflow import Workflow, WorkflowVersion
from app.modules.agent_identity.models import AgentIdentity
from app.modules.glens.entry_context import LensEntryContext, resolve_entry_context
from app.modules.glens.evidence_explanation import answer_from_result, refresh_saved_evidence
from app.modules.glens.platform_evidence import PlatformEvidenceQuery, read_platform_evidence
from app.modules.guard.event_access import restrict_event_query
from app.modules.guard.models import GuardAuditEvent
from app.runtime.accounting.request_evidence import AttemptEvidence


@pytest.fixture
def journey(monkeypatch):
    url = os.environ.get("LENS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("LENS_TEST_DATABASE_URL not set")
    monkeypatch.setattr("app.core.auth._clerk_enabled_dispatch", lambda: True)
    name = "lens_test_" + uuid4().hex
    admin = create_engine(url)
    engine = create_engine(url, connect_args={"options": f"-csearch_path={name}"})
    metadata = MetaData()
    def projection(model, names):
        return Table(model.__tablename__, metadata, *[
            Column(key, model.__table__.c[key].type, primary_key=key == "id") for key in names
        ])
    ids = projection(AgentIdentity, ["id", "workspace_id", "source", "owner_user_id"])
    events = projection(GuardAuditEvent, ["id", "workspace_id", "agent_identity_id", "request_id", "ts",
        "decision", "rule_id", "policy_hash", "provider", "model", "lifecycle_state", "execution_status",
        "clerk_user_id", "source", "conductai_run_id", "routing_meta"])
    receipts = projection(LlmAttemptReceipt, list(AttemptEvidence.__dataclass_fields__) + [
        "workspace_id", "agent_identity_id", "workflow_run_id", "source", "developer_external_id", "finalized_at"])
    workflows = projection(Workflow, ["id", "workspace_id", "name"])
    versions = projection(WorkflowVersion, ["id", "workflow_id"])
    runs = projection(Run, ["id", "workspace_id", "workflow_version_id", "triggered_by", "status",
        "current_block_id", "created_at", "started_at", "completed_at"])
    steps = projection(RunEvent, ["id", "run_id", "block_id", "kind", "created_at"])
    ws, other, agent, foreign_agent = [uuid4() for _ in range(4)]
    now = datetime.now(timezone.utc)
    with admin.begin() as connection:
        connection.execute(CreateSchema(name))
        connection.execute(text(f'CREATE ROLE "{name}" NOLOGIN NOSUPERUSER NOBYPASSRLS'))
    try:
        with engine.begin() as c:
            metadata.create_all(c)
            for sql in [
                "CREATE TABLE workspace_users (workspace_id uuid, clerk_user_id text, role text)",
                "CREATE TABLE roles (id integer, name text, workspace_id uuid)",
                "CREATE TABLE permissions (id integer, name text)",
                "CREATE TABLE role_permissions (role_id integer, permission_id integer)",
                "INSERT INTO roles VALUES (1, 'developer', NULL)",
                "INSERT INTO permissions VALUES (1, 'guard.activity.view_own'), (2, 'guard.spend.view_own'), (3, 'platform.runs.view')",
                "INSERT INTO role_permissions VALUES (1,1), (1,2), (1,3)",
            ]:
                c.execute(text(sql))
            for tenant, identity in [(ws, agent), (other, foreign_agent)]:
                c.execute(text("INSERT INTO workspace_users VALUES (:ws, 'alice', 'developer')"), {"ws": tenant})
                c.execute(ids.insert().values(id=str(identity), workspace_id=tenant, source="conduct_trial", owner_user_id="alice"))
            # Use the shipped policy, not a test-specific approximation. The
            # production migration intentionally excludes runs from RLS.
            path = Path(__file__).resolve().parents[2] / "alembic/versions/0004_rls_workspace_isolation.py"
            spec = importlib.util.spec_from_file_location("lens_rls_migration", path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            c.execute(text("ALTER TABLE workflows ENABLE ROW LEVEL SECURITY"))
            c.execute(text(migration._POLICY_SQL.format(table="workflows")))
            c.execute(text(f'GRANT USAGE ON SCHEMA "{name}" TO "{name}"'))
            c.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{name}" TO "{name}"'))

        def event(source="gateway", workspace=ws, identity=agent, expected=1, user="alice"):
            row = dict(id=uuid4(), workspace_id=workspace, agent_identity_id=str(identity), request_id=uuid4(),
                ts=now, decision="blocked", provider="anthropic", model="fixture-model", source=source,
                clerk_user_id=user, lifecycle_state="finalized", routing_meta={"attempts": [{}] * expected})
            with engine.begin() as c:
                c.execute(events.insert().values(**row))
            return row

        def receipt(row, ordinal=0, run_id=None, workspace=None, when=None):
            with engine.begin() as c:
                c.execute(receipts.insert().values(id=uuid4(), workspace_id=workspace or row["workspace_id"],
                    agent_identity_id=agent, request_id=row["request_id"], attempt_ordinal=ordinal,
                    provider="anthropic", model="fixture-model", contract_version=1, pricing_version="frozen-v1",
                    currency="USD", usage_origin="provider_reported", usage_completeness="complete",
                    pricing_completeness="priced", execution_outcome="failed" if ordinal == 0 else "succeeded",
                    total_input_tokens=100, total_output_tokens=20, cache_read_tokens=50,
                    reasoning_output_tokens=5, calculated_cost_microdollars=1200, workflow_run_id=run_id,
                    source=row["source"], developer_external_id=None, finalized_at=when or now))

        def run(workspace=ws, workflow_workspace=None):
            rid, wid, version = uuid4(), uuid4(), uuid4()
            with engine.begin() as c:
                c.execute(workflows.insert().values(id=wid, workspace_id=workflow_workspace or workspace, name="Deploy"))
                c.execute(versions.insert().values(id=version, workflow_id=wid))
                c.execute(runs.insert().values(id=rid, workspace_id=workspace, workflow_version_id=version,
                    triggered_by="alice", status="failed", current_block_id="ship", created_at=now))
                c.execute(steps.insert().values(id=uuid4(), run_id=rid, block_id="ship", kind="block_failed", created_at=now))
            return rid

        @contextmanager
        def reader(workspace=ws):
            with Session(engine) as db:
                db.execute(text(f'SET LOCAL ROLE "{name}"'))
                set_workspace_rls(db, workspace)
                yield db

        yield SimpleNamespace(ws=ws, other=other, agent=agent, foreign_agent=foreign_agent,
            engine=engine, reader=reader, event=event, receipt=receipt, run=run, now=now, role=name)
    finally:
        engine.dispose()
        with admin.begin() as c:
            c.execute(DropSchema(name, cascade=True))
            c.execute(text(f'DROP ROLE "{name}"'))
        admin.dispose()


def investigate(j, db, kind, resource=None, **kwargs):
    query = resolve_entry_context(db, j.ws, "alice", LensEntryContext(
        kind=kind, workspace_id=j.ws, resource_id=resource, **kwargs))
    evidence = read_platform_evidence(db, j.ws, "alice", query)
    answer, saved = answer_from_result(evidence.model_dump_json(), str(j.ws), "get_platform_evidence")
    return evidence, answer, saved


def test_gateway_window_totals_and_failed_attempts(journey):
    j = journey
    row = j.event(expected=2)
    j.receipt(row)
    j.receipt(row, 1)
    j.receipt(j.event(workspace=j.other, identity=j.foreign_agent))
    j.receipt(j.event(), when=j.now + timedelta(hours=1))
    with j.reader() as db:
        args = dict(surface="gateway", since=j.now - timedelta(hours=1),
                    until=j.now + timedelta(hours=1), limit=1)
        value = read_platform_evidence(db, j.ws, "alice", PlatformEvidenceQuery(intent="spend", **args))
        assert value.status == "ok"
        assert value.gateway_window.cost_microdollars == 2400
        assert value.gateway_window.attempt_count == 2
        assert len(value.gateway_window.attempts) == 1
        assert value.gateway_window.attempts[0].event_id == row["id"]
        failures = read_platform_evidence(db, j.ws, "alice", PlatformEvidenceQuery(intent="failures", **args))
        assert failures.gateway_window.attempt_count == 1
        assert failures.gateway_window.attempts[0].attempt_ordinal == 0


@pytest.mark.parametrize("source", ["hook", "mcp", "gateway", "proxy"])
def test_event_to_lens_to_authorized_citation(journey, source):
    j = journey
    row = j.event(source=source, expected=2)
    j.receipt(row)
    j.receipt(row, 1)
    foreign = j.event(workspace=j.other, identity=j.foreign_agent)
    with j.reader() as db:
        evidence, answer, _ = investigate(j, db, "event", row["id"])
        assert evidence.status == "ok"
        assert evidence.accounting_totals.calculated_cost_microdollars.value == 2400
        assert "input 200; output 40" in answer
        assert str(foreign["id"]) not in answer
        citation = restrict_event_query(db.query(GuardAuditEvent.id), db, j.ws, "alice", row["id"])
        assert citation.one().id == row["id"]
        assert f"/logs/guard?id={row['id']}" in answer


def test_workflow_step_receipt_link_and_rls_are_both_real(journey):
    j = journey
    run = j.run()
    j.run(workspace=j.other)
    malformed = j.run(workflow_workspace=j.other)
    row = j.event()
    j.receipt(row, run_id=run)
    with j.reader() as db:
        assert db.execute(text("SELECT count(*) FROM workflows")).scalar_one() == 1
        role = db.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
        assert not role.rolsuper and not role.rolbypassrls
        evidence, answer, _ = investigate(j, db, "run", run, block_id="ship")
        assert evidence.runs[0].source_id == run
        assert evidence.accounting_totals.calculated_cost_microdollars.value == 1200
        assert "run-wide, not step-specific" in answer
        with pytest.raises(HTTPException) as exc:
            investigate(j, db, "run", malformed)
        assert exc.value.status_code == 404


def test_saved_query_rechecks_revoked_spend_then_membership(journey):
    j = journey
    row = j.event()
    j.receipt(row)
    with j.reader() as db:
        _, _, saved = investigate(j, db, "event", row["id"])
    content = json.dumps({"evidence_tool": "get_platform_evidence", "evidence_query": saved})
    with j.engine.begin() as c:
        c.execute(text("DELETE FROM role_permissions WHERE permission_id=2"))
    with j.reader() as db:
        answer = refresh_saved_evidence(content, db, str(j.ws), "alice")
        assert "access denied" in answer and "$0.001200" not in answer
    with j.engine.begin() as c:
        c.execute(text("DELETE FROM workspace_users WHERE workspace_id=:ws"), {"ws": j.ws})
    with j.reader() as db:
        assert "do not have access" in refresh_saved_evidence(content, db, str(j.ws), "alice")


def test_trial_is_one_entry_point_and_wrong_workspace_receipt_is_excluded(journey):
    j = journey
    row = j.event()
    j.receipt(row, workspace=j.other)
    with j.reader() as db:
        evidence, answer, _ = investigate(j, db, "trial")
        assert len(evidence.records) == 1
        assert evidence.accounting_totals.receipt_count == 0
        assert "calculated cost unavailable" in answer


def test_registered_tool_sets_rls_on_its_own_session(journey, monkeypatch):
    from app.tools.registrations.lens.platform_evidence import get_platform_evidence
    j = journey
    rid = j.run()
    def session():
        db = Session(j.engine)
        db.execute(text(f'SET LOCAL ROLE "{j.role}"'))
        return db
    monkeypatch.setattr("app.core.database.SessionLocal", session)
    result = get_platform_evidence(SimpleNamespace(workspace_id=str(j.ws), clerk_user_id="alice"),
                                   surface="workflow", run_id=str(rid), exact_resource=True)
    assert result["runs_status"] == "ok"
    assert result["runs"][0]["source_id"] == str(rid)
