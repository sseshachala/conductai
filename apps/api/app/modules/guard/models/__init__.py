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


def _chain_lock(db, ws_uuid) -> None:
    """Serialise hash-chain appends for one workspace until the transaction ends.

    A transaction-scoped advisory lock, taken before reading the chain tail, so
    a writer that waited always sees the row the previous writer committed
    (a row lock on the old tail does not: the waiter keeps that old row and
    forks the chain). Re-entrant within one transaction. No-op off Postgres.
    """
    try:
        dialect = db.get_bind().dialect.name
    except Exception:  # noqa: BLE001 — test doubles / unbound sessions
        return
    if dialect != "postgresql":
        return
    from sqlalchemy import text

    key = int.from_bytes(hashlib.sha256(f"guard_audit_chain:{ws_uuid}".encode()).digest()[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


def _chain_tail(db, ws_uuid):
    return (
        db.query(GuardAuditEvent.entry_hash, GuardAuditEvent.ts)
        .filter(GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.entry_hash.isnot(None))
        .order_by(GuardAuditEvent.ts.desc(), GuardAuditEvent.id.desc())
        .first()
    )


def _entry_hash(ts: datetime, tool_call, decision: str, prev: str) -> str:
    return hashlib.sha256(f"{ts.isoformat()}|{tool_call or ''}|{decision}|{prev}".encode()).hexdigest()


def chain_hash_for_insert(db, ws_uuid, ts: datetime, tool_call, decision: str):
    """Returns (previous_hash, entry_hash) for a new GuardAuditEvent row.
    Holds the per-workspace chain lock until the caller's transaction ends."""
    _chain_lock(db, ws_uuid)
    last = _chain_tail(db, ws_uuid)
    prev = last.entry_hash if last else ""
    return prev, _entry_hash(ts, tool_call, decision, prev)


def chain_next(db, ws_uuid, tool_call, decision: str):
    """Returns (ts, previous_hash, entry_hash) with ``ts`` stamped under the lock.

    The verifier walks rows in (ts, id) order, so ``ts`` is taken after the
    lock and never earlier than the current tail (instances' clocks can
    differ by a few ms). Use the returned ``ts`` for the row.
    """
    from datetime import timedelta, timezone

    _chain_lock(db, ws_uuid)
    last = _chain_tail(db, ws_uuid)
    prev = last.entry_hash if last else ""
    ts = datetime.now(timezone.utc)
    if last and isinstance(last.ts, datetime):
        tail_ts = last.ts if last.ts.tzinfo else last.ts.replace(tzinfo=timezone.utc)
        if ts <= tail_ts:
            ts = tail_ts + timedelta(microseconds=1)
    return ts, prev, _entry_hash(ts, tool_call, decision, prev)
