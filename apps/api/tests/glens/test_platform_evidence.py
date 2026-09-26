"""Platform tool evidence uses real SQL, RBAC and the shared receipt reader."""
import json
from uuid import uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, Uuid, text

from app.models.run import Run, RunEvent
from app.models.workflow import Workflow, WorkflowVersion
from app.modules.glens.platform_evidence import PlatformEvidenceQuery, read_platform_evidence
from app.modules.glens.evidence_explanation import answer_from_result, refresh_saved_evidence
from tests.glens.test_trial_evidence import data, query, WS, OTHER, NOW  # noqa: F401
from tests.glens.test_trial_accounting import accounting, ALICE, BOB  # noqa: F401


@pytest.fixture
def platform(accounting):
    db, event, receipt = accounting
    for ddl in [
        "ALTER TABLE guard_audit_events ADD COLUMN clerk_user_id TEXT",
        "ALTER TABLE guard_audit_events ADD COLUMN source TEXT",
        "ALTER TABLE guard_audit_events ADD COLUMN conductai_run_id TEXT",
        "ALTER TABLE llm_attempt_receipts ADD COLUMN workflow_run_id TEXT",
        "INSERT INTO permissions VALUES (5, 'platform.runs.view')",
        "INSERT INTO role_permissions VALUES (1, 5), (2, 5)",
    ]:
        db.execute(text(ddl))
    metadata = MetaData()
    def projection(model, names):
        table = Table(model.__tablename__, metadata, *[
            Column(name, Uuid(native_uuid=False) if isinstance(model.__table__.c[name].type, Uuid)
                   else model.__table__.c[name].type, primary_key=name == "id") for name in names
        ])
        table.create(db.connection())
        return table
    workflows = projection(Workflow, ["id", "workspace_id", "name"])
    versions = projection(WorkflowVersion, ["id", "workflow_id"])
    runs = projection(Run, ["id", "workspace_id", "workflow_version_id", "triggered_by", "status",
                            "current_block_id", "created_at", "started_at", "completed_at"])
    steps = projection(RunEvent, ["id", "run_id", "block_id", "kind", "created_at"])
    def activity(source="gateway", user="alice", run_id=None, **kwargs):
        row = event(**kwargs)
        db.execute(text("UPDATE guard_audit_events SET source=:source, clerk_user_id=:user, conductai_run_id=:run WHERE id=:id"),
                   {"id": row["id"].hex, "source": source, "user": user, "run": str(run_id) if run_id else None})
        return row
    def run(user="alice", workspace=WS, workflow_workspace=None, count=2):
        wf, version, rid = uuid4(), uuid4(), uuid4()
        db.execute(workflows.insert().values(id=wf, workspace_id=workflow_workspace or workspace, name="Deploy"))
        db.execute(versions.insert().values(id=version, workflow_id=wf))
        db.execute(runs.insert().values(id=rid, workspace_id=workspace, workflow_version_id=version,
                                       triggered_by=user, status="failed", current_block_id="ship",
                                       created_at=NOW, started_at=NOW, completed_at=NOW))
        for i in range(count):
            db.execute(steps.insert().values(id=uuid4(), run_id=rid, block_id="ship",
                                            kind="block_failed" if i == 0 else "block_started", created_at=NOW))
        return rid
    return db, activity, receipt, run


def read(db, user="alice", **kwargs):
    args = query().model_dump()
    args.update(kwargs)
    return read_platform_evidence(db, str(WS), user, PlatformEvidenceQuery(**args))


def test_platform_is_not_restricted_to_trial_identities(platform):
    db, activity, receipt, run = platform
    db.execute(text("UPDATE agent_identities SET source='conduct_auto' WHERE id=:id"), {"id": str(ALICE)})
    row = activity()
    receipt(row)
    rid = run()
    evidence = read(db)
    assert evidence.status == "ok"
    assert evidence.records[0].source_id == row["id"]
    assert evidence.accounting_totals.input_tokens.value == 100
    assert evidence.runs[0].source_id == rid
    assert evidence.runs[0].steps_total == 2
    answer, saved = answer_from_result(evidence.model_dump_json(), str(WS), "get_platform_evidence")
    assert "Recorded Conduct Activity" in answer
    assert "Attempt 0" in answer
    assert f"/runs/{rid}" in answer
    assert "input 100; output 20" in answer
    assert saved["surface"] == "all"
    assert read(db, surface="trial").records == []


@pytest.mark.parametrize("surface,source", [("guard", "hook"), ("guard", "mcp"),
                                         ("gateway", "gateway"), ("gateway", "proxy"),
                                         ("workflow", "workflow")])
def test_surface_filters(platform, surface, source):
    db, activity, _, _ = platform
    target = activity(source=source)
    activity(source="other")
    evidence = read(db, surface=surface)
    assert [r.source_id for r in evidence.records] == [target["id"]]


def test_own_scope_and_malformed_tenant_links(platform):
    db, activity, _, run = platform
    mine = activity()
    activity(user="bob", identity=BOB)
    activity(user="bob", identity="foreign")
    activity(workspace=OTHER)
    own_run = run()
    run(user="bob")
    run(workspace=OTHER)
    run(workflow_workspace=OTHER)
    evidence = read(db)
    assert [r.source_id for r in evidence.records] == [mine["id"]]
    assert [r.source_id for r in evidence.runs] == [own_run]


def test_hook_without_agent_identity_uses_authenticated_owner(platform):
    db, activity, _, _ = platform
    mine = activity(source="hook", identity=None)
    activity(source="hook", user="bob", identity=None)
    evidence = read(db, surface="guard")
    assert [r.source_id for r in evidence.records] == [mine["id"]]
    assert evidence.accounting_unlinked_event_count == 1
    assert evidence.accounting_totals.input_tokens.value is None


def test_workspace_scope_and_run_permissions(platform):
    db, activity, _, run = platform
    activity(user="bob", identity=BOB)
    run(user="bob")
    assert read(db, scope="workspace").status == "denied"
    evidence = read(db, user="admin", scope="workspace")
    assert len(evidence.records) == len(evidence.runs) == 1
    db.execute(text("DELETE FROM role_permissions WHERE permission_id=5"))
    evidence = read(db, user="admin", scope="workspace")
    assert evidence.status == "ok" and evidence.runs_status == "denied"
    assert evidence.runs == []


def test_run_filter_links_gateway_receipts_without_double_counting(platform):
    db, activity, receipt, run = platform
    rid = run()
    row = activity()
    paid = receipt(row)
    db.execute(text("UPDATE llm_attempt_receipts SET workflow_run_id=:run WHERE id=:id"),
               {"run": rid.hex, "id": paid["id"].hex})
    activity()
    evidence = read(db, surface="workflow", run_id=rid)
    assert [r.source_id for r in evidence.records] == [row["id"]]
    assert evidence.accounting_totals.calculated_cost_microdollars.value == 1200
    assert evidence.runs[0].source_id == rid


def test_bounded_run_and_step_counts(platform):
    db, _, _, run = platform
    run(count=12)
    run(count=12)
    evidence = read(db, surface="workflow", limit=1)
    assert evidence.runs_status == "partial" and evidence.runs_total == 2
    assert evidence.runs[0].steps_total == 12 and len(evidence.runs[0].steps) == 10


def test_request_filter_does_not_attach_unrelated_runs(platform):
    db, activity, _, run = platform
    row = activity()
    run()
    evidence = read(db, request_ids=[row["request_id"]])
    assert evidence.runs_status == "not_requested" and evidence.runs == []


def test_platform_saved_query_rechecks_run_permission(platform):
    db, _, _, run = platform
    rid = run()
    evidence = read(db)
    _, saved = answer_from_result(evidence.model_dump_json(), str(WS), "get_platform_evidence")
    content = json.dumps({"evidence_query": saved, "evidence_tool": "get_platform_evidence"})
    assert f"/runs/{rid}" in refresh_saved_evidence(content, db, str(WS), "alice")
    db.execute(text("DELETE FROM role_permissions WHERE permission_id=5"))
    answer = refresh_saved_evidence(content, db, str(WS), "alice")
    assert f"/runs/{rid}" not in answer and "Workflow evidence: denied" in answer


def test_model_cannot_supply_tenant_or_user(platform):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PlatformEvidenceQuery(workspace_id=str(OTHER))
    with pytest.raises(ValidationError):
        PlatformEvidenceQuery(user_id="admin")
