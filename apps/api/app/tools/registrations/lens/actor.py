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
    ToolDef(
        name="update_budget",
        description=(
            "Update the monthly USD limit on a Guard spend budget by budget ID. "
            "Two-step: returns a pending action for the user to confirm; the "
            "confirm click writes the new limit + a hash-chained audit entry. "
            "Guard policy guard.spend.budgets.edit still applies."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "budget_id": {
                    "type": "string",
                    "description": "UUID of the guard_spend_budgets row to update.",
                },
                "monthly_limit_usd": {
                    "type": "number",
                    "description": "New monthly USD limit (>= 0).",
                },
            },
            "required": ["budget_id", "monthly_limit_usd"],
        },
        impl=_actor_impl("update_budget"),
        annotations=ToolAnnotations(read_only=False, destructive=False, idempotent=True),
        tags=_ACTOR_TAGS,
    ),
    ToolDef(
        name="install_pack",
        description=(
            "Install a marketplace skill pack into the workspace by slug. "
            "Two-step: returns a pending action for the user to confirm; the "
            "confirm click adds the WorkspaceSkillPack row and invalidates "
            "the policy cache. Guard policy guard.policies.edit still applies."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Pack slug (e.g. 'conduct-soc2').",
                },
            },
            "required": ["slug"],
        },
        impl=_actor_impl("install_pack"),
        annotations=ToolAnnotations(read_only=False, destructive=False, idempotent=True),
        tags=_ACTOR_TAGS,
    ),
    ToolDef(
        name="invite_member",
        description=(
            "Invite a new member to the workspace by email. Two-step: returns "
            "a pending action for the user to confirm; the confirm click "
            "inserts the workspace_invites row, fires the Clerk org invitation, "
            "and sends the templated email. Guard policy "
            "platform.members.manage still applies."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Email address of the person to invite.",
                },
                "role": {
                    "type": "string",
                    "description": "Workspace role (admin, developer, security, viewer).",
                },
            },
            "required": ["email", "role"],
        },
        impl=_actor_impl("invite_member"),
        annotations=ToolAnnotations(read_only=False, destructive=False, idempotent=True),
        tags=_ACTOR_TAGS,
    ),
    ToolDef(
        name="enable_policy",
        description=(
            "Enable a Guard policy rule by rule_id. Two-step: returns a pending "
            "action for the user to confirm; the confirm click flips the enabled "
            "flag + invalidates the policy cache. Guard policy guard.policies.edit "
            "still applies."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "rule_id": {
                    "type": "string",
                    "description": "Policy rule id (e.g. 'r-sr117-01').",
                },
            },
            "required": ["rule_id"],
        },
        impl=_actor_impl("enable_policy"),
        annotations=ToolAnnotations(read_only=False, destructive=False, idempotent=True),
        tags=_ACTOR_TAGS,
    ),
    ToolDef(
        name="disable_policy",
        description=(
            "Disable a Guard policy rule by rule_id. Two-step: returns a pending "
            "action for the user to confirm; the confirm click flips the enabled "
            "flag + invalidates the policy cache. Disabling a pack rule requires "
            "a reason (surfaces as a compliance exception in the audit trail)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "rule_id": {
                    "type": "string",
                    "description": "Policy rule id.",
                },
                "reason": {
                    "type": "string",
                    "description": "Required when disabling a pack rule. Surfaced in the audit trail.",
                },
            },
            "required": ["rule_id"],
        },
        impl=_actor_impl("disable_policy"),
        annotations=ToolAnnotations(read_only=False, destructive=False, idempotent=True),
        tags=_ACTOR_TAGS,
    ),
    ToolDef(
        name="deactivate_agent_identity",
        description=(
            "Deactivate an agent identity by id (security kill switch). Two-step: "
            "returns a pending action for the user to confirm; the confirm click "
            "sets lifecycle_state='deactivated' so the identity can no longer "
            "authenticate. Guard policy platform.members.manage still applies."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent identity id (UUID).",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason surfaced in the audit trail.",
                },
            },
            "required": ["agent_id"],
        },
        impl=_actor_impl("deactivate_agent_identity"),
        annotations=ToolAnnotations(read_only=False, destructive=False, idempotent=True),
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
