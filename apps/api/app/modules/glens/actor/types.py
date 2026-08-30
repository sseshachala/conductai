"""Types for the actor substrate — `ActionSpec`, `ProposeResult`, `ActionCtx`.

An `ActionSpec` is the pluggable unit for a mutating tool: two callables
(`propose` + `execute`), a Guard permission string, and a name. Read tools
use `ToolDef` directly; mutating tools additionally register an `ActionSpec`
so the substrate can drive the two-step confirm/execute flow.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session


@dataclass
class ProposeResult:
    """What a `propose` callable returns.

    Successful path: `summary` describes the pending action for the confirm
    card, `resolved_input` is the args after slug/name lookups (what will be
    persisted + passed to `execute`).

    Rejected path: `rejected=True` + `reason` — the tool never enters the
    approval flow. Use for static validation errors ("no workflow matches
    that slug", "you can't peer-approve your own request").
    """
    summary: str
    resolved_input: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    rejected: bool = False
    reason: str | None = None


@dataclass
class ActionCtx:
    """Runtime context handed to `propose` and `execute`.

    Built from `MCPContext` + the DB session for the current request. Never
    constructed by tool code — the substrate builds it in
    `_require_confirmation()` (propose phase) and in the confirm endpoint
    (execute phase).
    """
    db: Session
    workspace_id: str
    clerk_user_id: str | None
    user_email: str | None
    session_id: str | None
    agent_identity_id: str | None
    surface: str  # "lens" | "mcp" | "http" | ...


ProposeFn = Callable[[ActionCtx, dict[str, Any]], ProposeResult]
ExecuteFn = Callable[[ActionCtx, dict[str, Any]], dict[str, Any]]


@dataclass
class ActionSpec:
    """One mutating tool.

    `name` matches the paired `ToolDef.name` so the LLM-facing surface and
    the substrate agree on which tool a `guard_approval_requests` row
    represents.
    """
    name: str
    guard_permission: str
    propose: ProposeFn
    execute: ExecuteFn
    expires_in: timedelta = timedelta(minutes=5)
    description: str = ""
