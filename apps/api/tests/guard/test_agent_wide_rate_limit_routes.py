import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.guard.routers import rate_limits


@pytest.mark.parametrize("value", [0, -1, 1.5, "2", True, 2147483648])
def test_agent_cap_uses_strict_positive_integer_validation(value):
    with pytest.raises(ValidationError):
        rate_limits.RateLimitIn(agent_identity_id=uuid4(), rpm=value)


def test_foreign_identity_cannot_be_associated_with_a_workspace():
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None
    with pytest.raises(HTTPException) as error:
        rate_limits.upsert_rate_limit(rate_limits.RateLimitIn(agent_identity_id=uuid4(), rpm=2), str(uuid4()), "admin", db)
    assert error.value.status_code == 404
    db.add.assert_not_called(); db.commit.assert_not_called()


def test_agent_routes_require_budget_edit_permission():
    for route in rate_limits.router.routes:
        permissions = [getattr(d.call, "__conduct_permission__", None) or inspect.getclosurevars(d.call).nonlocals.get("permission") for d in route.dependant.dependencies
                       if inspect.isfunction(d.call)]
        assert "guard.spend.budgets.edit" in permissions


def test_agent_picker_query_is_workspace_scoped_and_returns_distinct_identities():
    db = MagicMock()
    rows = [SimpleNamespace(id="one", name="Worker"), SimpleNamespace(id="two", name="Worker")]
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = rows
    assert rate_limits.list_agent_options("workspace-a", "admin", db) == [
        {"id": "one", "name": "Worker"}, {"id": "two", "name": "Worker"},
    ]
    assert db.query.return_value.filter.call_args.args[0].right.value == "workspace-a"
