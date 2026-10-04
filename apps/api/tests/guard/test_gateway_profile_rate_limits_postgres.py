"""Real migration, tenant isolation and Redis quota tests in disposable resources."""
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import settings
from app.core.workspace_context import set_workspace_rls
from app.models.gateway_profile import GatewayProfileRateLimit
from app.modules.agent_identity.models import AgentIdentity
from app.modules.guard import gateway_profile_rate_limit as limiter
from app.routers.gateway_profiles_v2 import (
    ProfileRateLimitsBody, get_profile_rate_limits, update_profile_rate_limits,
)


@pytest.fixture
def database():
    if os.environ.get("GATEWAY_PROFILE_RATE_REAL_TESTS") != "1":
        pytest.skip("Set GATEWAY_PROFILE_RATE_REAL_TESTS=1 for PostgreSQL/Redis checks")
    schema, role = "profile_rate_" + uuid4().hex, "profile_rate_role_" + uuid4().hex
    admin = create_engine(settings.sqlalchemy_database_url)
    engine = create_engine(settings.sqlalchemy_database_url, connect_args={"options": f"-csearch_path={schema}"})
    ws, other, profile, sibling, legacy, agent, outsider = [uuid4() for _ in range(7)]
    path = Path(__file__).resolve().parents[2] / "alembic/versions/0163_gateway_profile_rate_limits.py"
    spec = importlib.util.spec_from_file_location("profile_rate_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with admin.begin() as conn:
        conn.execute(CreateSchema(schema))
        conn.execute(text(f'CREATE ROLE "{role}"'))
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE workspaces (id uuid PRIMARY KEY)"))
            conn.execute(text("INSERT INTO workspaces VALUES (:id), (:other)"), {"id": ws, "other": other})
            AgentIdentity.__table__.create(conn)
            for aid, workspace in ((agent, ws), (outsider, other)):
                conn.execute(text("""INSERT INTO agent_identities
                    (id,workspace_id,name,provider,token_prefix,token_encrypted,created_at)
                    VALUES (:id,:ws,'fixture worker','test','fixture','unused',now())"""), {"id": str(aid), "ws": workspace})
            conn.execute(text("""CREATE TABLE gateway_profiles (
                id uuid PRIMARY KEY,workspace_id uuid REFERENCES workspaces(id),environment_id uuid,
                name varchar(128),schema_version varchar(16),config jsonb NOT NULL DEFAULT '{}',
                working_copy jsonb,model_alias varchar(128),cond_code varchar(32),active_revision_id uuid,
                created_at timestamptz DEFAULT now(),updated_at timestamptz DEFAULT now())"""))
            for pid, version in ((profile, "2"), (sibling, "2"), (legacy, "1")):
                conn.execute(text("""INSERT INTO gateway_profiles
                    (id,workspace_id,name,schema_version,cond_code,active_revision_id)
                    VALUES (:id,:ws,'test',:version,:code,:revision)"""),
                    {"id": pid, "ws": ws, "version": version, "code": pid.hex[:8], "revision": uuid4()})
            conn.execute(text("""CREATE TABLE guard_rate_limits (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                workspace_id uuid NOT NULL REFERENCES workspaces(id),
                agent_identity_id varchar(36) REFERENCES agent_identities(id),
                rpm integer,tpm integer,created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT uq_guard_rate_limits_scope UNIQUE (workspace_id, agent_identity_id))"""))
            conn.execute(text("""INSERT INTO guard_rate_limits (workspace_id,agent_identity_id,rpm,tpm) VALUES
                (:ws,NULL,60,1000),(:ws,NULL,2,500),(:ws,:agent,1,100)"""), {"ws": ws, "agent": str(agent)})
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
            conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"'))
            conn.execute(text(f'GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA "{schema}" TO "{role}"'))
        yield engine, role, ws, other, profile, sibling, legacy, agent, outsider, migration
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
            conn.execute(text(f'DROP ROLE "{role}"'))
        admin.dispose()


def test_migration_preserves_defaults_agents_and_legacy_rows(database):
    engine, role, ws, _, profile, sibling, legacy, agent, _, _ = database
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT profile_id,agent_identity_id,rpm,tpm FROM gateway_profile_rate_limits")).all()
        assert {(r.profile_id, r.agent_identity_id, r.rpm, r.tpm) for r in rows} == {
            (pid, aid, rpm, tpm) for pid in (profile, sibling)
            for aid, rpm, tpm in ((None, 2, 500), (str(agent), 1, 100))
        }
        assert all(r.profile_id != legacy for r in rows)
        assert conn.execute(text("SELECT count(*) FROM guard_rate_limits")).scalar() == 3


def test_profile_saves_do_not_edit_global_agents_or_legacy_backups(database):
    engine, role, ws, _, profile, _, _, agent, _, _ = database
    with engine.connect() as conn:
        conn.execute(text(f'SET ROLE "{role}"')); conn.commit()
        with Session(bind=conn) as db:
            result = update_profile_rate_limits(str(ws), profile, ProfileRateLimitsBody(rpm=5, tpm=1000), db)
            assert result.rpm == 5 and result.tpm == 1000
            assert result.agent_limits == [] and result.available_agents == []
            result = update_profile_rate_limits(str(ws), profile, ProfileRateLimitsBody(rpm=None, agent_limits=[]), db)
            assert result.rpm is None and result.tpm is None and result.agent_limits == []
            assert get_profile_rate_limits(str(ws), profile, db).rpm is None
            assert db.execute(text("SELECT rpm FROM guard_rate_limits WHERE agent_identity_id=:id"), {"id": str(agent)}).scalar() == 1
            assert db.execute(text("SELECT rpm FROM gateway_profile_rate_limits WHERE profile_id=:pid AND agent_identity_id=:id"),
                              {"pid": profile, "id": str(agent)}).scalar() == 1


def test_foreign_agents_and_profiles_rejected(database):
    engine, _, ws, other, profile, _, _, _, outsider, _ = database
    with Session(engine) as db:
        with pytest.raises(HTTPException) as error:
            update_profile_rate_limits(str(ws), profile, ProfileRateLimitsBody(agent_limits=[{
                "agent_identity_id": outsider, "rpm": 1,
            }]), db)
        assert error.value.status_code == 400
        with pytest.raises(HTTPException) as error:
            get_profile_rate_limits(str(other), profile, db)
        assert error.value.status_code == 404


def test_rls_and_database_constraints_enforce_tenant_ownership(database):
    engine, role, ws, other, profile, _, _, _, outsider, _ = database
    with engine.begin() as conn:
        conn.execute(text(f'SET LOCAL ROLE "{role}"'))
        assert conn.execute(text("SELECT count(*) FROM gateway_profile_rate_limits")).scalar() == 0
        conn.execute(text("SELECT set_config('app.current_workspace', :ws, true)"), {"ws": str(other)})
        assert conn.execute(text("SELECT count(*) FROM gateway_profile_rate_limits")).scalar() == 0
        conn.execute(text("SELECT set_config('app.current_workspace', :ws, true)"), {"ws": str(ws)})
        assert conn.execute(text("SELECT count(*) FROM gateway_profile_rate_limits")).scalar() == 4
        cases = [
            {"ws": other, "profile": profile, "agent": None, "rpm": 1},
            {"ws": ws, "profile": profile, "agent": str(outsider), "rpm": 1},
            {"ws": ws, "profile": profile, "agent": None, "rpm": 0},
            {"ws": ws, "profile": profile, "agent": None, "rpm": 1},
        ]
        for params, code in zip(cases, ("42501", "23503", "23514", "23505")):
            with pytest.raises((IntegrityError, ProgrammingError)) as error:
                with conn.begin_nested():
                    conn.execute(text("""INSERT INTO gateway_profile_rate_limits (workspace_id,profile_id,agent_identity_id,rpm)
                        VALUES (:ws,:profile,:agent,:rpm)"""), params)
            assert error.value.orig.pgcode == code


def test_downgrade_does_not_silently_delete_new_caps_under_rls(database):
    engine, _, _, _, _, _, _, _, _, migration = database
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)), pytest.raises(RuntimeError, match="Export profile rate limits"):
            migration.downgrade()


def test_real_redis_atomic_shared_admission_settlement_and_outage(database, monkeypatch):
    engine, _, ws, _, profile, _, _, _, _, _ = database
    import redis
    client = redis.from_url(settings.redis_url, decode_responses=True)
    client.ping()
    monkeypatch.setattr(limiter, "_redis_client", lambda: client)
    prefix = f"guard:prl:{{{ws}}}:profile:{profile}:"

    def request(_):
        with Session(engine) as db:
            set_workspace_rls(db, ws)
            return limiter.check_profile_rate_limit(db, workspace_id=str(ws), profile_id=profile,
                revision_id=uuid4(), agent_identity_id=None, reserved_tokens=200)

    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            decisions = list(pool.map(request, range(20)))
        accepted = [d for d in decisions if not d.limited]
        assert len(accepted) == 2
        from types import SimpleNamespace
        plan = SimpleNamespace(operation="openai_chat_completions", last_meta={"attempts": [{"succeeded": True}]},
            upstream_body=bytearray(b'{"usage":{"prompt_tokens":10,"completion_tokens":5}}'))
        limiter.settle_profile_rate_limit(accepted[0].admission, plan)
        keys = list(client.scan_iter(match=prefix + "*"))
        assert sorted(int(client.get(key)) for key in keys) == [2, 215]
        # Only our unique profile keys are touched. No outages are injected into
        # the shared Redis service or any running deployment.
        monkeypatch.setattr(limiter, "_redis_client", lambda: (_ for _ in ()).throw(ConnectionError("test outage")))
        assert request(0).status == 503
    finally:
        keys = list(client.scan_iter(match=prefix + "*"))
        if keys:
            client.delete(*keys)


def test_agent_cap_edit_scoped_to_its_workspace_and_serializes_creation(database):
    from app.modules.guard.routers.rate_limits import RateLimitIn, upsert_rate_limit
    engine, _, ws, other, profile, _, _, agent, outsider, _ = database
    with Session(engine) as db:
        with pytest.raises(HTTPException) as error:
            upsert_rate_limit(RateLimitIn(agent_identity_id=outsider, rpm=10), str(ws), "admin", db)
        assert error.value.status_code == 404
        result = upsert_rate_limit(RateLimitIn(agent_identity_id=agent, rpm=10, tpm=200), str(ws), "admin", db)
        assert result.agent_identity_id == str(agent) and result.rpm == 10
        set_workspace_rls(db, ws)
        assert get_profile_rate_limits(str(ws), profile, db).rpm == 2
    # No cap exists for this identity yet. Concurrent first saves must upsert,
    # not race into a unique-constraint failure.
    def save(_):
        with Session(engine) as db:
            return upsert_rate_limit(RateLimitIn(agent_identity_id=outsider, rpm=3), str(other), "admin", db)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(save, range(12)))
    assert len({r.id for r in results}) == 1


def test_migration_promotes_strictest_agent_caps_and_preserves_backups(database):
    engine, role, ws, other, profile, sibling, _, agent, outsider, _ = database
    path = Path(__file__).resolve().parents[2] / "alembic/versions/0164_agent_wide_gateway_rate_limits.py"
    spec = importlib.util.spec_from_file_location("agent_wide_migration", path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as conn:
        conn.execute(text("UPDATE guard_rate_limits SET rpm=100,tpm=NULL WHERE agent_identity_id=:id"), {"id": str(agent)})
        conn.execute(text("UPDATE gateway_profile_rate_limits SET rpm=10,tpm=200 WHERE profile_id=:pid AND agent_identity_id=:id"),
                     {"pid": profile, "id": str(agent)})
        conn.execute(text("UPDATE gateway_profile_rate_limits SET rpm=20,tpm=150 WHERE profile_id=:pid AND agent_identity_id=:id"),
                     {"pid": sibling, "id": str(agent)})
        conn.execute(text("""INSERT INTO gateway_profiles (id,workspace_id,name,schema_version)
            VALUES (:id,:ws,'other','2')"""), {"id": outsider, "ws": other})
        conn.execute(text("""INSERT INTO gateway_profile_rate_limits (workspace_id,profile_id,agent_identity_id,rpm)
            VALUES (:ws,:pid,:agent,3)"""), {"ws": other, "pid": outsider, "agent": str(outsider)})
        conn.execute(text(f'SET LOCAL ROLE "{role}"'))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        rows = conn.execute(text("SELECT workspace_id,agent_identity_id,rpm,tpm FROM guard_rate_limits WHERE agent_identity_id IS NOT NULL")).all()
        assert set(rows) == {(ws, str(agent), 10, 150), (other, str(outsider), 3, None)}
        conn.execute(text("SELECT set_config('app.current_workspace', :ws, true)"), {"ws": str(ws)})
        assert conn.execute(text("SELECT count(*) FROM gateway_profile_rate_limits WHERE agent_identity_id IS NOT NULL")).scalar() == 2
        assert conn.execute(text("SELECT rpm FROM gateway_profile_rate_limits WHERE profile_id=:pid AND agent_identity_id=:id"),
                            {"pid": sibling, "id": str(agent)}).scalar() == 20


def test_real_redis_agent_cap_cannot_be_bypassed_by_changing_profiles(database, monkeypatch):
    import redis
    engine, _, ws, _, first, second, _, agent, _, _ = database
    client = redis.from_url(settings.redis_url, decode_responses=True); client.ping()
    monkeypatch.setattr(limiter, "_redis_client", lambda: client)
    prefix = f"guard:prl:{{{ws}}}:"
    def request(profile):
        with Session(engine) as db:
            set_workspace_rls(db, ws)
            return limiter.check_profile_rate_limit(db, workspace_id=str(ws), profile_id=profile,
                revision_id=uuid4(), agent_identity_id=str(agent), reserved_tokens=10)
    try:
        assert not request(first).limited
        refused = request(second)
        assert refused.limited and refused.scope == "agent" and refused.metric == "rpm"
        keys = list(client.scan_iter(match=prefix + "*"))
        assert len(keys) == 4 and not any(str(second) in key for key in keys)
    finally:
        keys = list(client.scan_iter(match=prefix + "*"))
        if keys:
            client.delete(*keys)
