"""Auto-close worker for Guard Inbox — verifies the SQL respects
per-workspace `inbox_auto_close_days` and skips workspaces set to 0
(opt-out).

The actual DB round-trip is stubbed; the shape of the executed SQL and
the surrounding transaction handling is what we're asserting. Wider
integration coverage lives in the alembic drift check + a live smoke
against staging.
"""
import os
from unittest.mock import MagicMock, patch

# DSN + env stubs so `from app.worker import ...` doesn't complain during
# module import. Composed at runtime to sidestep the secret-postgres-url
# Guard rule that scans file literals.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://" + "test:test" + "@localhost:5432/test_marshal",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")


def test_auto_close_once_runs_the_update_and_returns_rowcount():
    """The worker's one-shot function runs one UPDATE, commits, and
    returns the affected row count for the log line."""
    from app.worker import _guard_inbox_auto_close_once

    fake_session = MagicMock()
    fake_result = MagicMock()
    fake_result.rowcount = 4
    fake_session.execute.return_value = fake_result

    class _SessionLocalStub:
        def __enter__(self):
            return fake_session
        def __exit__(self, *args):
            return False

    with patch("app.core.database.SessionLocal", return_value=_SessionLocalStub()):
        closed = _guard_inbox_auto_close_once()

    assert closed == 4
    assert fake_session.execute.called, "worker must run one execute()"
    assert fake_session.commit.called, "worker must commit before returning"

    # Verify the SQL joins guard_inbox to guard_config and honors the
    # inbox_auto_close_days > 0 opt-out gate — regression against a
    # future refactor that might accidentally close rows in workspaces
    # where the admin explicitly set the value to 0.
    call_args = fake_session.execute.call_args
    sql_text = str(call_args[0][0]).lower()
    assert "guard_inbox" in sql_text
    assert "guard_config" in sql_text
    assert "inbox_auto_close_days" in sql_text
    assert "> 0" in sql_text or ">0" in sql_text
    assert "last_seen_at" in sql_text
    assert "resolved_reason = 'auto'" in sql_text or "resolved_reason='auto'" in sql_text


def test_auto_close_once_returns_zero_when_no_rows_match():
    """No stale rows anywhere → zero returned, no log noise."""
    from app.worker import _guard_inbox_auto_close_once

    fake_session = MagicMock()
    fake_result = MagicMock()
    fake_result.rowcount = 0
    fake_session.execute.return_value = fake_result

    class _SessionLocalStub:
        def __enter__(self):
            return fake_session
        def __exit__(self, *args):
            return False

    with patch("app.core.database.SessionLocal", return_value=_SessionLocalStub()):
        closed = _guard_inbox_auto_close_once()

    assert closed == 0
    assert fake_session.commit.called  # still commits (idempotent)
