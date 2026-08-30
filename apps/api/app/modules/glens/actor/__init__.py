"""Lens actor substrate — pluggable mutating tool framework (#1297).

Every mutating Lens/MCP tool implements an `ActionSpec` and registers it
against `default_action_registry`. The substrate handles Guard pre-flight,
`guard_approval_requests` row creation with `surface='lens'`, confirm/cancel
routing, and dispatch to `spec.execute()`. Adding a new mutating tool =
one `ActionSpec` + one paired `ToolDef` — no per-tool endpoints or audit.

See #1282 (parent epic) + #1297 (this substrate).
"""
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult
from app.modules.glens.actor.registry import (
    ActionRegistry,
    default_action_registry,
)

__all__ = [
    "ActionCtx",
    "ActionSpec",
    "ProposeResult",
    "ActionRegistry",
    "default_action_registry",
]
