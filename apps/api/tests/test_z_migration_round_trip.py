"""Alembic upgrade+downgrade round-trip suite — #1261.

Two probes:

1. Downgrade last 10 revisions one step at a time, then re-upgrade head.
   Catches non-idempotent upgrades and broken downgrade steps.

2. `alembic check` after re-upgrade. Asserts the resulting schema still
   matches the SQLAlchemy metadata — catches drift where model + revision
   silently diverge.

Named `test_z_*` so it runs LAST — the round-trip leaves the DB at head,
but the intermediate state during the loop is inconsistent and would
break any test that ran concurrently against the shared DB.

The try/finally guarantees the DB is returned to head even if a downgrade
mid-loop raises, so a broken migration in this suite does not corrupt
the rest of the pytest run.

Marker `migration` — runs by default in per-PR CI. Opt-out with
`-m 'not migration'` when needed for local iteration.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal


API_DIR = Path(__file__).resolve().parent.parent  # apps/api/


def _db_available() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable")


def _alembic(*args: str) -> str:
    r = subprocess.run(
        ["alembic", *args],
        cwd=API_DIR,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (
        f"alembic {' '.join(args)} failed (exit {r.returncode}):\n"
        f"stdout:\n{r.stdout}\n"
        f"stderr:\n{r.stderr}"
    )
    return r.stdout


@requires_db
@pytest.mark.migration
def test_downgrade_last_10_then_upgrade_head():
    """Roll back the last 10 revisions one step at a time, then re-upgrade head.

    If ANY downgrade step or the final re-upgrade fails, the finally block
    guarantees the DB returns to head so downstream tests keep passing.
    """
    try:
        for step in range(10):
            _alembic("downgrade", "-1")
    finally:
        _alembic("upgrade", "head")


@requires_db
@pytest.mark.migration
def test_alembic_check_no_schema_drift():
    """`alembic check` compares the live schema against the SQLAlchemy
    metadata. Passes only if the two are in sync."""
    _alembic("check")
