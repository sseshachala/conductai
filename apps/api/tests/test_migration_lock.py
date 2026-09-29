from unittest.mock import MagicMock, patch

import pytest

from app.core.migration_lock import migration_lock


def test_lock_is_released_on_migration_failure():
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = True
    with pytest.raises(ValueError):
        with migration_lock(connection):
            raise ValueError("migration failed")
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert "pg_try_advisory_lock" in statements[0]
    assert "pg_advisory_unlock" in statements[-1]
    connection.rollback.assert_called_once()


def test_busy_migration_fails_without_running_or_unlocking_another_owner():
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = False
    with pytest.raises(RuntimeError, match="Another Conduct schema migration"):
        with migration_lock(connection, timeout_seconds=0):
            pytest.fail("Should never run migration")
    assert connection.execute.call_count == 1


def test_contending_startup_waits_then_acquires():
    connection = MagicMock()
    connection.execute.return_value.scalar_one.side_effect = [False, True]
    with patch("app.core.migration_lock.time.sleep") as sleep:
        with migration_lock(connection):
            pass
    sleep.assert_called_once_with(0.1)
    assert connection.execute.call_count == 3
