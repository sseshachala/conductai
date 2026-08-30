"""Lens actor tools — mutating tool ToolDefs paired with actor ActionSpecs.

Each entry here is the LLM-facing surface of an ActionSpec registered in
`app.modules.glens.actor.registrations`. The ToolDef.impl returns a confirm
envelope; the real mutation runs when the user hits
POST /glens/actions/{id}/confirm.

Adding a new mutating tool = add both:
  1. ActionSpec in app.modules.glens.actor.registrations.<name>
  2. ToolDef here, impl=_actor_impl("<name>")
"""
from __future__ import annotations

from app.tools.types import ToolAnnotations, ToolDef
from app.tools.registrations.lens._shared import _actor_impl, _ACTOR_TAGS


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
]
