"""Focused invariants; actual authentication and SQL live in the standalone harness."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.auth.federation.delegation_schemas import BindingWrite, PrincipalWrite
from app.modules.auth.federation.resolver import FederationDenied, _live


@pytest.fixture
def records():
    workspace, bid, pid = uuid4(), uuid4(), uuid4()
    common = dict(workspace_id=workspace, status="active", actions=["mcp.guard_check", "mcp.guard_check_prompt"])
    binding = SimpleNamespace(id=bid, **common)
    principal = SimpleNamespace(id=pid, **common)
    grant = SimpleNamespace(binding_id=bid, principal_id=pid,
                            expires_at=datetime.now(timezone.utc) + timedelta(hours=1), **common)
    return workspace, binding, principal, grant


def test_intersection_is_exact_and_request_scoped(records):
    workspace, binding, principal, grant = records
    principal.actions = ["mcp.guard_check"]
    assert _live(None, workspace, binding, principal, grant, "mcp.guard_check") == ("mcp.guard_check",)
    with pytest.raises(FederationDenied, match="action_forbidden"):
        _live(None, workspace, binding, principal, grant, "mcp.guard_check_prompt")


@pytest.mark.parametrize("index,field,value", [
    (1, "status", "disabled"), (2, "status", "disabled"), (3, "status", "disabled"),
    (1, "workspace_id", uuid4()), (2, "workspace_id", uuid4()), (3, "workspace_id", uuid4()),
    (3, "binding_id", uuid4()), (3, "principal_id", uuid4()),
    (1, "actions", []), (2, "actions", []), (3, "actions", []),
])
def test_revocation_and_cross_binding_deny(records, index, field, value):
    setattr(records[index], field, value)
    with pytest.raises(FederationDenied):
        _live(None, *records, "mcp.guard_check")


def test_expired_or_missing_grant(records):
    workspace, binding, principal, grant = records
    grant.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    for candidate in (grant, None):
        with pytest.raises(FederationDenied, match="grant_invalid"):
            _live(None, workspace, binding, principal, candidate, "mcp.guard_check")


@pytest.mark.parametrize("actions", [["*"], ["mcp.*"], ["mcp.conduct_run_workflow"], []])
def test_unsupported_scope_cannot_be_approved(actions):
    with pytest.raises(ValidationError):
        BindingWrite(expected_revision=0, status="active", actions=actions,
                     caller_id=uuid4(), connection_id=uuid4())


def test_principal_cannot_auto_map_console_roles():
    with pytest.raises(ValidationError):
        PrincipalWrite(expected_revision=0, status="active", actions=["mcp.guard_check"],
                       issuer="https://issuer.example", subject="user-1", kind="human", role="admin")
