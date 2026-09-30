"""Display labels round-trip without changing identity or authorization."""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.auth.federation.delegation_models import FederationPrincipal
from app.modules.auth.federation.delegation_router import save
from app.modules.auth.federation.delegation_schemas import PrincipalWrite
from app.modules.auth.federation.management import approval_output


def body(**changes):
    return PrincipalWrite(**{ "expected_revision": 1, "status": "active",
        "actions": ["mcp.guard_check_prompt"], "issuer": "https://idp.example",
        "subject": "alice-subject", "kind": "human", **changes })


@pytest.mark.parametrize("name,expected", [(" Alice ", "Alice"), ("", None), ("  ", None), (None, None)])
def test_name_normalization(name, expected):
    assert body(display_name=name).display_name == expected


@pytest.mark.parametrize("name", ["a" * 201, 123, ["Alice"]])
def test_name_validation(name):
    with pytest.raises(ValidationError):
        body(display_name=name)


@pytest.mark.parametrize("changes,expected", [({}, "Alice"), ({"display_name": "Renamed"}, "Renamed"),
                                           ({"display_name": None}, None)])
def test_update_preserves_omitted_name_and_round_trips(changes, expected):
    row = FederationPrincipal(id=uuid4(), workspace_id=uuid4(), revision=1,
        issuer="https://idp.example", subject="alice-subject", kind="human",
        status="active", actions=["mcp.guard_check_prompt"], display_name="Alice")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    result = save(db, FederationPrincipal, row.id, row.workspace_id, body(**changes),
                  ("issuer", "subject", "kind"), "admin", "admin")
    assert result["display_name"] == expected
    assert approval_output(row, PrincipalWrite)["display_name"] == expected
    assert row.subject == "alice-subject" and row.actions == ["mcp.guard_check_prompt"]
    db.commit.assert_called_once()


def test_legacy_create_without_name():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    result = save(db, FederationPrincipal, uuid4(), uuid4(), body(expected_revision=0),
                  ("issuer", "subject", "kind"), "admin", "admin")
    assert result["display_name"] is None


def test_rename_cannot_change_subject():
    row = FederationPrincipal(id=uuid4(), workspace_id=uuid4(), revision=1,
        issuer="https://idp.example", subject="alice-subject", kind="human", display_name="Alice")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    with pytest.raises(HTTPException) as error:
        save(db, FederationPrincipal, row.id, row.workspace_id,
             body(subject="bob-subject", display_name="Bob"), ("issuer", "subject", "kind"), "admin", "admin")
    assert error.value.status_code == 409
    db.commit.assert_not_called()
