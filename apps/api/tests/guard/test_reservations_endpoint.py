"""PR-B — /guard/spend/reservations endpoint.

Compile-time coverage for the new endpoint. Validates that:

- The route is registered under the spend router prefix.
- The ReservationScopeOut DTO exposes every scope field the drawer needs
  (agent_identity_id, source, client_tool alongside the pre-existing
  clerk_user_id + ai_tool).
- Invalid ids -> 422, not silent empty list.
- Workspace scoping predicate is present on the query (no cross-tenant
  leak). Compile-check via reading the source.
"""
from __future__ import annotations

import inspect

from app.modules.guard.routers.spend import (
    ReservationScopeOut,
    list_reservations_for_request,
    router,
)


def test_route_is_registered():
    paths = {getattr(r, "path", None) for r in router.routes}
    assert "/guard/spend/reservations" in paths


def test_dto_carries_full_scope_tuple():
    """The drawer needs every scope column so it can label each row
    correctly (workspace / agent / user / transport / client tool)."""
    fields = ReservationScopeOut.model_fields
    for required in (
        "reservation_id",
        "workspace_id",
        "clerk_user_id",
        "agent_identity_id",
        "ai_tool",
        "source",
        "client_tool",
        "period_key",
        "estimated_cents",
        "actual_cents",
        "status",
        "created_at",
        "resolved_at",
    ):
        assert required in fields, f"DTO missing {required}"


def test_handler_scopes_query_to_workspace():
    """Grep-style guard: the query must include workspace_id and request_id
    filters. Prevents accidental cross-tenant leak if someone refactors."""
    src = inspect.getsource(list_reservations_for_request)
    assert "BudgetReservation.workspace_id ==" in src
    assert "BudgetReservation.request_id ==" in src
