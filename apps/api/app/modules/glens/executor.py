"""Executor — Lens request-scoped context holder.

All `_tool_*` methods that used to live on this class have been migrated
to top-level `def impl(ctx, ...)` functions in the matching
`app/tools/registrations/lens/<domain>.py` files (epic #1655). This
class survives only because a few Lens code paths still construct one
to carry `db`, `workspace_id`, and `agent_identity_id` (used by
guarded_llm_call for egress attribution).

If callers stop constructing Executor, the class itself can be deleted.
"""
from sqlalchemy.orm import Session


class Executor:

    def __init__(self, db: Session, workspace_id: str, agent_identity_id: str | None = None):
        self.db = db
        self.workspace_id = workspace_id
        # Set on chat endpoints so guarded_llm_call/stream can attribute egress
        # to the session-scoped AgentIdentity. None outside chat (tool registrations).
        self.agent_identity_id = agent_identity_id
