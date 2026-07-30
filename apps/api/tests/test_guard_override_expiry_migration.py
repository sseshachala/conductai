import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch


MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0089_guard_override_expiry.py"
)


def test_legacy_relaxing_overrides_receive_grace_expiry():
    spec = importlib.util.spec_from_file_location("guard_override_expiry_0089", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    connection = MagicMock()
    with patch.object(module.op, "add_column"), patch.object(
        module.op, "get_bind", return_value=connection
    ), patch.object(module.op, "drop_column"):
        module.upgrade()

    sql = "\n".join(str(call.args[0]) for call in connection.execute.call_args_list)
    assert "INTERVAL '7 days'" in sql
    assert "disabled IS TRUE" in sql
    assert "action IS NOT NULL" in sql
    assert "match_pattern IS NOT NULL" not in sql
    assert "DELETE FROM guard_policy_cache" in sql
