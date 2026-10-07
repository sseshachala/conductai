"""ConductGuard ORM models.

Split by concern into submodules; every model is re-exported here so
``from app.modules.guard.models import X`` keeps working. Importing this
package imports every submodule, so all mappers register on ``Base``.
"""
import hashlib
from datetime import datetime

from app.modules.guard.models.config import (  # noqa: F401 — re-exports
    GuardConfig, GuardMemberConfig, GuardNotificationChannel, GuardSession,
)
from app.modules.guard.models.audit import (  # noqa: F401 — re-exports
    GuardAuditArchiveSegment, GuardAuditEvent, GuardAuditRetentionHold,
)
from app.modules.guard.models.spend import (  # noqa: F401 — re-exports
    BudgetReservation, GuardDeveloperTools, GuardRateLimit, GuardSavings, GuardSpendBudget,
    SessionReport,
)
from app.modules.guard.models.policy import (  # noqa: F401 — re-exports
    DiscoveredAgent, DiscoveryScan, GuardKnowledgeIndex, GuardPolicyCache, GuardRuleOverride,
    GuardVerifyRun, PolicyCertification, SkillPack, WorkspaceCustomRule, WorkspaceSigningKey,
    WorkspaceSkillPack,
)
from app.modules.guard.models.projection import (  # noqa: F401 — re-exports
    GuardApprovalRequest, GuardInbox, GuardProjectionIntent, GuardProjectionSummary,
)


def get_policy_hash(db, ws_uuid, persona: str = "agent") -> str | None:
    """Snapshot the active policy version_hash for a workspace at decision time. Returns None if no cache yet."""
    row = db.get(GuardPolicyCache, (ws_uuid, persona))
    return row.version_hash if row else None


def chain_hash_for_insert(db, ws_uuid, ts: datetime, tool_call, decision: str):
    """Returns (previous_hash, entry_hash) for a new GuardAuditEvent row.
    Acquires a per-workspace row lock to serialise concurrent inserts."""
    last = (
        db.query(GuardAuditEvent.entry_hash)
        .filter(GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.entry_hash.isnot(None))
        .order_by(GuardAuditEvent.ts.desc())
        .with_for_update(skip_locked=False)
        .first()
    )
    prev = last.entry_hash if last else ""
    _tool = tool_call or ""
    entry = hashlib.sha256(f"{ts.isoformat()}|{_tool}|{decision}|{prev}".encode()).hexdigest()
    return prev, entry
