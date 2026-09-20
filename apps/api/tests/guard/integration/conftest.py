"""Integration fixtures for /gateway/v1/completions (#2144 PR 1 follow-up).

Every test in this directory needs REAL Postgres + REAL Redis. The chaos
docker-compose at ``tests/chaos/docker-compose.yml`` provides both on
non-standard ports so it co-exists with the dev DB. To run:

    docker compose -f tests/chaos/docker-compose.yml up -d
    # then export GATEWAY_IT_DB_URL and GATEWAY_IT_REDIS_URL to match
    # the ports declared in that compose file
    ./.venv/bin/python -m pytest tests/guard/integration -x

If the env vars aren't set, every collected test skips — a plain
``pytest`` run without docker does not blow up in CI.

The fixture stack:

- session-scoped: alembic migrated engine
- autouse per-test: wipe workspaces/agent_identities/gateway_profiles*/
  audit_log/integrations; flush Redis; clear gateway_revision_cache +
  auth_cache
- monkeypatch ``app.core.database.SessionLocal`` to bind to the chaos
  engine so ``handle_gateway_request``'s direct ``SessionLocal()`` calls
  hit the integration DB, not the dev DB
- monkeypatch ``get_provider_transport_registry`` so outbound HTTP never
  leaves the process — the stub returns a canned OpenAI Chat Completions
  response

ponytail: one file, factories inline. Split only if additional integration
tests want distinct factories per scenario.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import time
import uuid
from typing import Any

import pytest


_DB_URL = os.environ.get("GATEWAY_IT_DB_URL")
_REDIS_URL = os.environ.get("GATEWAY_IT_REDIS_URL")

_SKIP_REASON = (
    "gateway integration suite needs GATEWAY_IT_DB_URL + GATEWAY_IT_REDIS_URL. "
    "Start docker compose -f tests/chaos/docker-compose.yml up -d, then set "
    "the env vars to the ports declared in that compose file."
)


def pytest_collection_modifyitems(config, items):  # noqa: D401
    """Skip everything under tests/guard/integration/ when env vars unset."""
    if _DB_URL and _REDIS_URL:
        return
    marker = pytest.mark.skip(reason=_SKIP_REASON)
    for item in items:
        if "tests/guard/integration/" in str(item.fspath).replace(os.sep, "/"):
            item.add_marker(marker)


# ─── session engine + migrations ───────────────────────────────────


@pytest.fixture(scope="session")
def _it_engine():
    from sqlalchemy import create_engine, text

    engine = create_engine(_DB_URL, future=True, pool_pre_ping=True)
    deadline = time.monotonic() + 30
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("select 1"))
            break
        except Exception:
            if time.monotonic() > deadline:
                pytest.skip("integration Postgres never became reachable")
            time.sleep(0.5)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def _it_migrated(_it_engine):
    """Run alembic upgrade head once per session."""
    env = os.environ.copy()
    env["DATABASE_URL"] = _DB_URL
    api_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    venv_python = os.path.join(api_root, ".venv", "bin", "python")
    if not os.path.exists(venv_python):
        pytest.skip(
            f"venv Python not found at {venv_python} — run "
            "'python3.11 -m venv .venv' in apps/api first"
        )
    result = subprocess.run(
        [venv_python, "-m", "alembic", "upgrade", "head"],
        env=env,
        cwd=api_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            "alembic upgrade head failed against integration Postgres:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    # Import every model so SQLAlchemy metadata resolves FKs at insert time.
    from app.models import workspace  # noqa: F401
    from app.modules.guard import models  # noqa: F401
    from app.models import gateway_profile  # noqa: F401
    from app.models import audit_log  # noqa: F401
    from app.modules.agent_identity import models as _ai_models  # noqa: F401
    from app.models import integration as _int_model  # noqa: F401
    return _it_engine


# ─── per-test cleanup ─────────────────────────────────────────────


_TABLES_TO_WIPE = [
    # ``guard_audit_events`` is where Guard writes gateway decisions — the
    # ``audit_log`` model in app/models/audit_log.py is a different, platform-
    # level audit surface and is not touched by the gateway path.
    "guard_audit_events",
    "audit_log",
    "budget_reservations",
    "gateway_profile_revisions",
    "gateway_profiles",
    "agent_identities",
    "integrations",
    "workspaces",
]


@pytest.fixture(autouse=True)
def _clean_integration_state(_it_migrated):
    """Wipe every table this suite touches; flush Redis; clear caches."""
    from sqlalchemy import text

    engine = _it_migrated
    with engine.begin() as conn:
        for tbl in _TABLES_TO_WIPE:
            try:
                conn.execute(text(f"truncate table {tbl} cascade"))
            except Exception:
                # Table may not exist in this migration set — skip.
                pass

    import redis as _redis
    r = _redis.Redis.from_url(_REDIS_URL)
    try:
        r.flushall()
    finally:
        r.close()

    try:
        from app.modules.guard.gateway_revision_cache import clear as _clear_rev
        _clear_rev()
    except Exception:
        pass
    try:
        from app.core.auth_cache import get_auth_cache as _get_auth_cache
        c = _get_auth_cache()
        if c is not None and hasattr(c, "clear"):
            c.clear()
    except Exception:
        pass
    yield


# ─── DB session wired to integration engine ───────────────────────


@pytest.fixture()
def it_db(_it_migrated):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=_it_migrated, expire_on_commit=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()


# ─── monkeypatch SessionLocal + Redis URL so app code hits the integration infra ──


@pytest.fixture(autouse=True)
def _rebind_session_and_redis(monkeypatch: pytest.MonkeyPatch, _it_migrated):
    """Rebind ``SessionLocal`` + ``REDIS_URL`` so calls inside
    ``handle_gateway_request`` (which uses ``SessionLocal()`` directly)
    hit the integration DB, not the dev DB.
    """
    from sqlalchemy.orm import sessionmaker

    IntegrationSession = sessionmaker(
        bind=_it_migrated, expire_on_commit=False, future=True,
    )
    monkeypatch.setattr("app.core.database.SessionLocal", IntegrationSession)

    # Modules that do ``from app.core.database import SessionLocal`` at
    # module TOP bind the name once at first import — a later monkeypatch
    # on ``app.core.database.SessionLocal`` does NOT rebind their local
    # copy. The BackgroundTask audit writer in ``app.guard.audit`` is
    # the case that bit us: when unit tests import ``guard.audit`` before
    # this fixture fires, the audit background task keeps writing to the
    # dev DB even though every foreground call hits the integration DB.
    # Patch every top-level rebind we depend on here.
    for _mod in (
        "app.guard.audit",
    ):
        try:
            monkeypatch.setattr(f"{_mod}.SessionLocal", IntegrationSession)
        except AttributeError:
            pass

    # Some modules cache the settings.redis_url at import time; setting the
    # env var ensures any fresh Redis client picks it up.
    monkeypatch.setenv("REDIS_URL", _REDIS_URL)

    # Force Gateway Profile v2 on for every integration test — otherwise
    # requests carrying a cond-<code>-<alias> model land on the 501 rollout
    # gate. This suite is proving out v2 behavior explicitly; the rollout
    # canary is a production-only concern.
    from app.core.config import settings as _settings
    monkeypatch.setattr(_settings, "guard_gateway_profile_v2", True, raising=False)
    monkeypatch.setattr(_settings, "guard_gateway_profile_v2_rollout_pct", 100, raising=False)


# ─── outbound transport stub ─────────────────────────────────────


class _StubTransport:
    """Captures the outbound call and returns a canned OpenAI response.

    Attributes set by the fixture, read by the test.
    """

    name = "raw_http_stub"

    def __init__(self, canned_response: dict[str, Any]):
        self.canned = canned_response
        self.calls: list[dict[str, Any]] = []

    def create_client(self, **kwargs):  # noqa: D401
        return self  # unused in v2 path but present for Protocol compat

    async def forward(self, **kwargs):
        self.calls.append(kwargs)
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=200, content=self.canned)


@pytest.fixture()
def stub_openai_transport(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch the transport registry so outbound HTTP never leaves the
    process. Returns the ``_StubTransport`` instance so tests can inspect
    what was forwarded.
    """
    canned = {
        "id": "chatcmpl-stub-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "pong"},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
    }
    stub = _StubTransport(canned)

    class _Registry:
        def for_provider(self, provider: str):
            return stub

    monkeypatch.setattr(
        "app.runtime.provider_transport.get_provider_transport_registry",
        lambda: _Registry(),
    )

    # v2 dispatches through NativeHTTPTransport.execute() which fires a real
    # httpx call to the vendor. Replace it with a coroutine that records the
    # call and returns the canned OpenAI response as a dict, matching the
    # non-streaming contract the v2 executor expects.
    async def _fake_execute(self, *, target, operation, payload, credential_resolver,
                            stream=False, client_headers=None):
        # Mirror what NativeHTTPTransport.execute would send upstream: the
        # payload verbatim with ``model`` rewritten to the target's own
        # model id. Tests assert against ``dispatched_body`` because that
        # is the wire-level fact — a bypass that reached the transport
        # without the rewrite would show up here as the caller's alias.
        dispatched_body = dict(payload)
        dispatched_body["model"] = target.model
        stub.calls.append({
            "target_id": target.id,
            "target_model": target.model,
            "operation": operation,
            "dispatched_body": dispatched_body,
            "stream": stream,
        })
        return dict(stub.canned)

    monkeypatch.setattr(
        "app.runtime.native_http_transport.NativeHTTPTransport.execute",
        _fake_execute,
    )

    # The v2 executor also resolves an upstream key from vault before it
    # hands the request to the transport. Since our stub never actually
    # calls upstream, any non-empty string satisfies the credential check
    # — patch every import path that would otherwise hit the real vault.
    _fake_key_fn = lambda *args, **kwargs: "sk-openai-fake-integration"
    monkeypatch.setattr(
        "app.modules.guard.gateway_credentials.resolve_gateway_key",
        _fake_key_fn,
    )
    monkeypatch.setattr(
        "app.runtime.gateway_v2_bridge.resolve_gateway_key",
        _fake_key_fn,
    )
    monkeypatch.setattr(
        "app.modules.guard.gateway_runtime.resolve_gateway_key",
        _fake_key_fn,
    )
    return stub


# ─── seed factory: workspace + agent token + published v2 profile ─


def _mint_agent_token(db, workspace_id: str) -> tuple[str, str]:
    """Insert an AgentIdentity row and return (token_str, identity_id).

    Token format follows ``cond_agt_<random>`` per ``core.auth``. The row
    stores the first 13 chars in ``token_prefix`` and the encrypted full
    token in ``token_encrypted`` so ``resolve_agent_token`` can match it
    on incoming requests.
    """
    from datetime import datetime, timezone

    from app.core.crypto import encrypt
    from app.modules.agent_identity.models import AgentIdentity

    # cond_api_ is the API-token prefix: workspace-scoped credential with no
    # guard_member_config linkage requirement. cond_agt_ is a session token
    # and requires a live GMC row, which this fixture deliberately does not
    # create — headless gateway callers use API tokens, not session tokens.
    token = f"cond_api_{secrets.token_hex(16)}"
    ident_id = str(uuid.uuid4())
    ident = AgentIdentity(
        id=ident_id,
        workspace_id=uuid.UUID(workspace_id),
        name="it-token",
        token_prefix=token[:13],
        token_encrypted=encrypt({"token": token}),
        # token_type="api" skips the guard_member_config + workspace-membership
        # checks in _resolve_agent_token. API tokens are workspace credentials
        # (no user login binding) so they authenticate directly. Matches
        # what `conduct login` mints for headless / machine-to-machine
        # callers of the gateway.
        token_type="api",
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(ident)
    db.commit()
    return token, ident_id


def _publish_v2_profile(
    db,
    *,
    workspace_id: str,
    cond_code: str,
    alias: str = "gpt-4o",
    target_provider: str = "openai",
    target_model: str = "openai/gpt-4o",
) -> tuple[str, str]:
    """Insert integration + revision + profile rows. Returns (profile_id, revision_id).

    The revision snapshot is a valid ``GatewayProfileV2`` JSON. The target
    uses a native_http transport pointing at a fake vault credential — the
    actual outbound is stubbed by ``stub_openai_transport``, so the vault
    lookup only needs to succeed, not resolve to a real upstream key.
    """
    from app.models.integration import Integration
    from app.core.crypto import encrypt

    env_id = str(uuid.uuid4())
    integ = Integration(
        workspace_id=uuid.UUID(workspace_id),
        environment_id=None,
        service="openai",
        auth_method="api_key",
        handle="openai",
        encrypted_credentials=encrypt({"api_key": "sk-openai-fake"}),
    )
    db.add(integ)
    db.commit()

    credential_ref = f"vault://{env_id}/openai-key"
    config = {
        "schema_version": 2,
        "name": f"it-profile-{cond_code}",
        "model_alias": alias,
        "accepts": ["openai_chat_completions"],
        "timeout_seconds": 30,
        "max_attempts": 1,
        "targets": [{
            "id": "primary",
            "transport": "native_http",
            "provider": target_provider,
            "model": target_model,
            "credential_ref": credential_ref,
            "provider_options": {},
        }],
    }

    from app.models.gateway_profile import GatewayProfile, GatewayProfileRevision

    # FK chain: revisions.profile_id → profiles.id, profiles.active_revision_id → revisions.id.
    # Insert profile with active_revision_id=NULL, then revision, then UPDATE.
    revision_id = uuid.uuid4()
    profile_id = uuid.uuid4()

    profile = GatewayProfile(
        id=profile_id,
        workspace_id=uuid.UUID(workspace_id),
        environment_id=None,
        name=f"it-profile-{cond_code}",
        schema_version="2",
        config={},
        model_alias=alias,
        cond_code=cond_code,
        active_revision_id=None,
    )
    db.add(profile)
    db.commit()

    revision = GatewayProfileRevision(
        id=revision_id,
        profile_id=profile_id,
        version=1,
        snapshot=config,
        published_by="it-fixture",
    )
    db.add(revision)
    db.commit()

    profile.active_revision_id = revision_id
    db.commit()
    return str(profile_id), str(revision_id)


@pytest.fixture()
def seeded_profile(it_db, stub_openai_transport):
    """One workspace + one agent token + one published v2 profile.

    Returns dict with: workspace_id, agent_token, agent_identity_id,
    cond_code, alias, profile_id, revision_id, stub_transport.
    """
    from app.models.workspace import Workspace

    ws = Workspace(name=f"it-ws-{secrets.token_hex(4)}")
    it_db.add(ws)
    it_db.commit()
    workspace_id = str(ws.id)

    token, identity_id = _mint_agent_token(it_db, workspace_id)
    cond_code = secrets.token_hex(4)  # 8 chars — matches _COND_CODE_RE
    alias = "gpt-4o"
    profile_id, revision_id = _publish_v2_profile(
        it_db,
        workspace_id=workspace_id,
        cond_code=cond_code,
        alias=alias,
    )
    return {
        "workspace_id": workspace_id,
        "agent_token": token,
        "agent_identity_id": identity_id,
        "cond_code": cond_code,
        "alias": alias,
        "profile_id": profile_id,
        "revision_id": revision_id,
        "profile_identifier": f"cond-{cond_code}-{alias}",
        "stub_transport": stub_openai_transport,
    }


# ─── FastAPI test app ────────────────────────────────────────────


@pytest.fixture()
def gateway_app():
    from fastapi import FastAPI
    from app.modules.guard.routers import gateway_proxy

    app = FastAPI()
    app.include_router(gateway_proxy.router)
    return app
