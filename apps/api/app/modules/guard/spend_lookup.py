"""Multi-scope budget lookup for the all-permit reservation contract.

Given a request scope ``(workspace, agent, transport, client_tool)`` — plus
the optional ``clerk_user_id`` for hook-originated requests — return every
budget row whose scope applies to the request. A row applies when each of
its scope fields either matches the request's value or is NULL ("any").

The all-permit contract (per the corrected design in PR-A) requires **every
returned row to permit the request**. The caller iterates the list and
reserves against each; a single insufficient budget refuses the whole
request and the ledger unwinds any partial holds atomically.

Precedence is intentionally NOT encoded here. Rows have no ordering meaning
under all-permit — the tightest applicable cap wins by construction because
its reserve() call is the one that fails first.

The ``ai_tool`` column on ``guard_spend_budgets`` is a shared field: an
admin can store either a **transport** identifier ('gateway', 'mcp', ...)
or a **client tool** identifier ('cursor', 'claude-code', ...) in it. The
frontend disambiguates via ``<optgroup>`` labels; the backend query matches
either interpretation because either is a legitimate scope the request has.
Trust model note: client_tool is descriptive unless signed via Agent
Identity (deferred to a follow-up PR); a caller cannot escape a
transport-scoped cap by mislabelling client_tool because transport is
authoritative (server-stamped).
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.guard.models import GuardSpendBudget


def lookup_applicable_budgets(
    db: Session,
    workspace_id: uuid.UUID,
    *,
    agent_identity_id: Optional[str] = None,
    transport: Optional[str] = None,
    client_tool: Optional[str] = None,
    clerk_user_id: Optional[str] = None,
) -> list[GuardSpendBudget]:
    """Return every budget row applicable to the given request scope.

    A row applies when workspace matches AND (for each scope field) either
    the row is scoped to that exact value or the row is null (any).

    Args:
        db: SQLAlchemy session.
        workspace_id: Request's workspace. Non-null.
        agent_identity_id: Request's agent identity (post-PR-0.5b invariant:
            required for gateway/MCP transports).
        transport: Request's transport ('gateway' | 'mcp' | 'workflow' |
            'runtime'). Server-stamped, authoritative.
        client_tool: Request's client-declared tool ('cursor', 'claude-code',
            free string, or None for unknown). Descriptive; do not use for
            security decisions unless signed via Agent Identity.
        clerk_user_id: Request's human user (present on hook-originated calls,
            None on machine-only paths).

    Returns:
        List of applicable ``GuardSpendBudget`` rows, ordered by created_at
        ascending. May be empty (no matching budget = no cap applies).
    """
    q = db.query(GuardSpendBudget).filter(
        GuardSpendBudget.workspace_id == workspace_id,
        or_(
            GuardSpendBudget.clerk_user_id.is_(None),
            GuardSpendBudget.clerk_user_id == clerk_user_id,
        ),
        or_(
            GuardSpendBudget.agent_identity_id.is_(None),
            GuardSpendBudget.agent_identity_id == agent_identity_id,
        ),
    )

    # ai_tool matcher: null (workspace-wide) OR matches transport OR matches
    # client_tool. Both are valid ways to key the ai_tool column — the shared
    # field ambiguity is by design (see module docstring).
    candidates = [v for v in (transport, client_tool) if v is not None]
    if candidates:
        q = q.filter(
            or_(
                GuardSpendBudget.ai_tool.is_(None),
                GuardSpendBudget.ai_tool.in_(candidates),
            )
        )
    else:
        q = q.filter(GuardSpendBudget.ai_tool.is_(None))

    return q.order_by(GuardSpendBudget.created_at.asc()).all()
