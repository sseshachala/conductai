"""Serialize API/Gateway startup migrations against their shared database."""
import time
from contextlib import contextmanager

from sqlalchemy import text

# Stable PostgreSQL advisory-lock namespace for Conduct schema migrations.
LOCK_NAMESPACE = 1129270852
LOCK_ID = 1


@contextmanager
def migration_lock(connection, *, timeout_seconds=30):
    deadline = time.monotonic() + timeout_seconds
    acquired = False
    try:
        while not acquired:
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(:namespace, :key)"),
                {"namespace": LOCK_NAMESPACE, "key": LOCK_ID},
            ).scalar_one()
            # The lock is session-scoped. End SQLAlchemy's implicit transaction
            # before Alembic opens the migration transaction and reads its head.
            connection.commit()
            if not acquired:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Another Conduct schema migration is running; retry deployment")
                time.sleep(0.1)
        yield
    finally:
        if acquired:
            connection.rollback()
            connection.execute(
                text("SELECT pg_advisory_unlock(:namespace, :key)"),
                {"namespace": LOCK_NAMESPACE, "key": LOCK_ID},
            )
            connection.commit()
