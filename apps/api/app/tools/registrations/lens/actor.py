"""Lens actor tools — mutating tool ToolDefs paired with actor ActionSpecs.

Each mutating entry is the LLM-facing surface of an `ActionSpec` registered in
`app.modules.glens.actor.registrations`. The `ToolDef.impl` returns a confirm
envelope; the real mutation runs when the user hits
`POST /glens/actions/{id}/confirm` — either via the ActionConfirmBubble button
OR via the `confirm_pending_action` chat tool (#1465).

Adding a new mutating tool = add both:
  1. `ActionSpec` in `app.modules.glens.actor.registrations.<name>`
  2. `ToolDef` here with `impl=_actor_impl("<name>")`

The `confirm_pending_action` / `cancel_pending_action` tools at the bottom of
this file are the chat-surface glue for step 2 — they let the LLM resolve a
natural-language "yes" / "no" against a pending row's `dispatch_confirm` /
`dispatch_cancel` service functions.
"""
from __future__ import annotations

from typing import Any

from app.tools.types import ToolAnnotations, ToolDef
from app.tools.registrations.lens._shared import _actor_impl, _ACTOR_TAGS


def _confirm_pending_action_impl(ctx, pending_action_id: str) -> dict[str, Any]:
    """LLM-callable confirm — same server logic as the ActionConfirmBubble
    button. Enforces proposer identity + session_id match so a compromised
    LLM in another session can't decide this one's pending actions."""
    from app.core.database import SessionLocal
    from app.modules.glens.actor.helpers import ConfirmError, dispatch_confirm

    db = SessionLocal()
    try:
        try:
            payload = dispatch_confirm(
                db,
                action_id=pending_action_id,
                workspace_id=ctx.workspace_id,
                clerk_user_id=getattr(ctx, "clerk_user_id", None),
                user_email=getattr(ctx, "user_email", None),
                role="admin",  # HTTP layer already validated the permission
                session_id=getattr(ctx, "session_id", None),
            )
        except ConfirmError as exc:
            return {"error": exc.detail, "status_code": exc.status_code}
        return payload
    finally:
        db.close()


def _cancel_pending_action_impl(
    ctx, pending_action_id: str, reason: str | None = None,
) -> dict[str, Any]:
    """LLM-callable cancel — same server logic as the Cancel button."""
    from app.core.database import SessionLocal
    from app.modules.glens.actor.helpers import ConfirmError, dispatch_cancel

    db = SessionLocal()
    try:
        try:
            payload = dispatch_cancel(
                db,
                action_id=pending_action_id,
                workspace_id=ctx.workspace_id,
                clerk_user_id=getattr(ctx, "clerk_user_id", None),
                user_email=getattr(ctx, "user_email", None),
                reason=reason,
                session_id=getattr(ctx, "session_id", None),
            )
        except ConfirmError as exc:
            return {"error": exc.detail, "status_code": exc.status_code}
        return payload
    finally:
        db.close()


TOOLS: list[ToolDef] = [
    ToolDef(
        name="decide_approval",
        description=(
            "Approve or reject a pending Guard approval request. Two-step: "
            "returns a pending action for the user to confirm; the confirm "
            "click writes the decision to guard_approval_requests and resumes "
            "any paused workflow run. Semantically identical to the Slack "
            "Approve/Reject buttons."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "approval_request_id": {
                    "type": "string",
                    "description": "UUID of the pending approval to decide.",
                },
                "decision": {
                    "type": "string",
                    "enum": ["approved", "rejected"],
                    "description": "Whether to approve or reject the request.",
                },
                "reason": {
                    "type": "string",
                    "description": "Required when rejecting. Surfaced in audit + notifications.",
                },
            },
            "required": ["approval_request_id", "decision"],
        },
        impl=_actor_impl("decide_approval"),
        annotations=ToolAnnotations(read_only=False, destructive=False, idempotent=True),
        tags=_ACTOR_TAGS,
    ),
    ToolDef(
        name="run_workflow",
        description=(
            "Trigger a workflow run by playbook slug, workflow ID, or name. "
            "Two-step: returns a pending action for the user to confirm; the "
            "confirm click inserts the Run and enqueues it via the same code "
            "path `conduct run` uses. Guard policy platform.workflows.run "
            "still applies."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name_or_id": {
                    "type": "string",
                    "description": "Workflow UUID, playbook slug, or workflow name (case-insensitive).",
                },
                "inputs": {
                    "type": "object",
                    "description": "Optional key/value overrides for run initial_state.",
                },
            },
            "required": ["name_or_id"],
        },
        impl=_actor_impl("run_workflow"),
        annotations=ToolAnnotations(read_only=False, destructive=False, idempotent=False),
        tags=_ACTOR_TAGS,
    ),
    # ── Chat-surface confirmation shortcut tools (#1465) ────────────────────
    # These let the LLM resolve natural-language "yes" / "no" replies against
    # a pending action without requiring a button click. Same server code as
    # the endpoint — session_id enforcement blocks cross-session confirmations.
    ToolDef(
        name="confirm_pending_action",
        description=(
            "Confirm a pending actor action (previously proposed via decide_approval, "
            "run_workflow, or another actor tool). Use when the user replies 'yes' / "
            "'go ahead' / 'confirm' to a confirmation card. Runs spec.execute for the "
            "underlying action and returns the result."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "pending_action_id": {
                    "type": "string",
                    "description": "UUID of the pending action (from the confirmation envelope's approval_request_id).",
                },
            },
            "required": ["pending_action_id"],
        },
        impl=_confirm_pending_action_impl,
        annotations=ToolAnnotations(read_only=False, destructive=False, idempotent=True),
        tags=_ACTOR_TAGS,
    ),
    ToolDef(
        name="cancel_pending_action",
        description=(
            "Cancel a pending actor action. Use when the user replies 'no' / "
            "'cancel' / 'stop' to a confirmation card. Marks the action rejected; "
            "no side effects."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "pending_action_id": {
                    "type": "string",
                    "description": "UUID of the pending action to cancel.",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason surfaced in audit + notifications.",
                },
            },
            "required": ["pending_action_id"],
        },
        impl=_cancel_pending_action_impl,
        annotations=ToolAnnotations(read_only=False, destructive=False, idempotent=True),
        tags=_ACTOR_TAGS,
    ),
]
