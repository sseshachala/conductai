"""Shared fixtures for the budget-ledger chaos suite.

Every test here needs REAL Postgres + REAL Redis running on the ports
declared in ``docker-compose.yml``. If the env vars are unset the tests
skip so a normal ``pytest`` run does not require Docker.
"""
from __future__ import annotations

import os
import subprocess
import time
import uuid

import pytest


CHAOS_DB_URL = os.environ.get("CHAOS_DB_URL")
CHAOS_REDIS_URL = os.environ.get("CHAOS_REDIS_URL")

# NB: module-level ``pytestmark`` in a conftest does NOT propagate to
# collected test items — we skip inside each session fixture instead so
# CI (no docker stack, no env vars) doesn't blow up trying to connect.
_SKIP_REASON = (
    "chaos suite requires CHAOS_DB_URL + CHAOS_REDIS_URL. Start the "
    "docker stack in tests/chaos/docker-compose.yml first."
)


def pytest_collection_modifyitems(config, items):
    """Skip every chaos-suite item when the env vars are unset. Runs at
    collection time so nothing tries to hit a nonexistent DB in CI."""
    if CHAOS_DB_URL and CHAOS_REDIS_URL:
        return
    skip_marker = pytest.mark.skip(reason=_SKIP_REASON)
    for item in items:
        # Only skip items collected under this conftest's directory.
        if "tests/chaos/" in str(item.fspath).replace(os.sep, "/"):
            item.add_marker(skip_marker)


# ─── Postgres ────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def chaos_engine():
    """A SQLAlchemy engine pointed at the chaos Postgres."""
    from sqlalchemy import create_engine

    engine = create_engine(CHAOS_DB_URL, future=True, pool_pre_ping=True)
    # Wait up to 30s for the container to be ready.
    deadline = time.monotonic() + 30
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(_text("select 1"))
            break
        except Exception:
            if time.monotonic() > deadline:
                pytest.skip("chaos Postgres never became reachable")
            time.sleep(0.5)
    yield engine
    engine.dispose()


def _text(sql):
    from sqlalchemy import text
    return text(sql)


@pytest.fixture(scope="session")
def chaos_migrated(chaos_engine):
    """Apply every Alembic migration to the chaos Postgres once per session."""
    # Point alembic at the chaos DB.
    env = os.environ.copy()
    env["DATABASE_URL"] = CHAOS_DB_URL
    # apps/api = parent of tests/ = two levels up from this conftest.
    api_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    # Use the venv's Python so alembic gets the same interpreter the
    # rest of the tests use. Otherwise system Python 3.9 tries to
    # import model files that require 3.10+ union syntax.
    venv_python = os.path.join(api_root, ".venv", "bin", "python")
    if not os.path.exists(venv_python):
        pytest.skip(
            f"venv Python not found at {venv_python} — run 'python3 -m venv .venv' "
            "in apps/api first"
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
            "alembic upgrade head failed against chaos Postgres:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return chaos_engine


@pytest.fixture(scope="session", autouse=True)
def _register_all_models(chaos_migrated):
    """Import every model that declares a table so SQLAlchemy can resolve
    FKs at insert time. Without this, ``budget_reservations.workspace_id``
    can't find the ``workspaces`` table metadata."""
    # These imports register Table objects on the shared MetaData.
    from app.models import workspace  # noqa: F401
    from app.modules.guard import models  # noqa: F401
    return chaos_migrated


@pytest.fixture()
def chaos_db(chaos_migrated, _register_all_models):
    """A per-test session against the chaos Postgres. Session commits are
    real — use ``clean_chaos_state`` fixture to wipe rows between tests."""
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=chaos_migrated, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()


# ─── Redis ───────────────────────────────────────────────────────────


@pytest.fixture()
def chaos_redis():
    """A raw Redis client pointed at the chaos Redis container."""
    import redis

    client = redis.Redis.from_url(CHAOS_REDIS_URL, decode_responses=True)
    deadline = time.monotonic() + 15
    while True:
        try:
            client.ping()
            break
        except Exception:
            if time.monotonic() > deadline:
                pytest.skip("chaos Redis never became reachable")
            time.sleep(0.5)
    yield client
    try:
        client.close()
    except Exception:
        pass


# ─── Cleanup between tests ───────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_chaos_state(chaos_migrated):
    """Wipe the ledger's mutable state before each test so leftover
    rows from a previous test cannot leak."""
    engine = chaos_migrated
    with engine.begin() as conn:
        conn.execute(_text("truncate table budget_reservations cascade"))
        conn.execute(_text("truncate table guard_audit_events cascade"))
        conn.execute(_text("truncate table workspaces cascade"))
    import redis

    client = redis.Redis.from_url(CHAOS_REDIS_URL)
    try:
        client.flushall()
    except Exception:
        pass
    finally:
        try:
            client.close()
        except Exception:
            pass
    yield


# ─── Ledger fixture pointed at chaos infra ───────────────────────────


@pytest.fixture()
def chaos_ledger(chaos_redis):
    """A BudgetLedger instance wired to the chaos Redis client."""
    from app.core.budget_ledger import BudgetLedger

    return BudgetLedger(redis_client=chaos_redis)


@pytest.fixture()
def warm_ledger(chaos_ledger, chaos_db, unique_workspace_id):
    """A ledger that has already been reconciled for ``unique_workspace_id``
    so ``reserve()`` returns ACCEPTED instead of NOT_READY. Mirrors what
    the server does at startup for allowlisted workspaces."""
    chaos_ledger.reconcile(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
    )
    return chaos_ledger


@pytest.fixture()
def unique_workspace_id(chaos_db):
    """Insert a real workspace row and return its id. The
    ``budget_reservations.workspace_id`` FK needs a real target row."""
    from app.models.workspace import Workspace

    ws = Workspace(name=f"chaos-{uuid.uuid4().hex[:8]}")
    chaos_db.add(ws)
    chaos_db.commit()
    return str(ws.id)
