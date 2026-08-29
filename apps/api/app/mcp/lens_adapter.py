"""LensAdapter — Lens chat consumes the same ToolRegistry as the MCP surfaces.

Lens chat historically dispatched tools via `Executor.call(name, args)` which
did its own `getattr(self, f"_tool_{name}")` lookup. That path was parallel to
the MCP HTTP/stdio adapters and had its own per-tool guard_check flow. Any
tool added to the ToolRegistry was invisible to Lens until the Executor got
a matching method — a permanent drift risk (#1219 / #1227).

This adapter closes the loop: Lens chat calls `lens_adapter.dispatch(name,
args_json, ctx)` and gets back the same JSON envelope `Executor.call` used to
produce. Under the hood it looks up the ToolDef in `default_registry`,
runs the composable policy engine (same shape as `app/mcp/server.py::dispatch`
but with `provider="lens"`), and invokes `tool.impl(ctx, **args)`.

Contract mirrors the legacy `Executor.call`:

- Returns a JSON string (chat.py passes it back to the model as tool result)
- Unknown tool → `{"error": "Unknown tool: <name>"}`
- Guard BLOCK → `{"error": "Blocked by Guard rule ...", "blocked_by": ..., "rule_id": ...}`
- Impl exception → `{"error": "<message>"}`
- Otherwise → `json.dumps(impl_return_value)`

Every registered Lens ToolDef's impl (see `app/tools/registrations/lens.py`)
already opens its own SessionLocal + Executor and dispatches to
`_tool_{method_name}` — so the adapter does not need to hold DB state.
"""
from __future__ import annotations

import json

import structlog

from app.guard.policy import evaluate_composed
from app.guard.policy_types import PolicyAction, PolicyContext
from app.mcp.server import MCPContext
from app.tools.registry import default_registry

log = structlog.get_logger(__name__)


def dispatch(name: str, arguments_json: str, ctx: MCPContext) -> str:
    """Look up tool in registry, run guard_check, invoke impl.

    Signature matches `Executor.call(name, arguments)` so the chat handler
    swap is one line. `arguments_json` is a JSON-encoded object; empty
    string is treated as `{}`.
    """
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid arguments JSON: {e}"})

    tool = default_registry.get(name)
    if tool is None:
        return json.dumps({"error": f"Unknown tool: {name}"})

    # Per-tool policy gate — same shape Executor.call used (#1218 Step 4).
    # provider="lens" so rules can scope to the Lens surface independently
    # of MCP/HTTP callers.
    policy_ctx = PolicyContext(
        workspace_id=ctx.workspace_id,
        clerk_user_id=ctx.clerk_user_id,
        provider="lens",
        model="tool",
        body={"tool_name": name, "arguments": args},
        extras={"kind": "lens_tool", "tool_name": name, "surface": ctx.surface},
    )
    try:
        decision = evaluate_composed(policy_ctx)
    except Exception as e:
        # Guard eval itself broke — fail-open, matches Executor.call behaviour.
        log.warning("lens_adapter.guard_check_failed", tool=name, err=str(e))
        decision = None

    if decision is not None and decision.action == PolicyAction.BLOCK:
        log.warning("lens_adapter.blocked",
                    tool=name,
                    rule=decision.rule_id,
                    source=decision.source)
        return json.dumps({
            "error": (
                f"Blocked by Guard rule {decision.rule_id}: "
                f"{decision.reason or 'policy violation'}"
            ),
            "blocked_by": decision.source,
            "rule_id": decision.rule_id,
        })

    try:
        return json.dumps(tool.impl(ctx, **args))
    except Exception as e:
        log.warning("lens_adapter.impl_error", tool=name, err=str(e))
        return json.dumps({"error": str(e)})
