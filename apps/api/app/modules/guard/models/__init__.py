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


def _tail_ts(db, ws_uuid):
    """Lock the chain and return ``(tail_row_or_None, ts)`` with ``ts`` stamped under the lock."""
    from datetime import timedelta, timezone

    _chain_lock(db, ws_uuid)
    last = _chain_tail(db, ws_uuid)
    ts = datetime.now(timezone.utc)
    if last and isinstance(last.ts, datetime):
        tail_ts = last.ts if last.ts.tzinfo else last.ts.replace(tzinfo=timezone.utc)
        if ts <= tail_ts:
            ts = tail_ts + timedelta(microseconds=1)
    return last, ts


def chain_begin(db, ws_uuid):
    """Returns ``(ts, previous_hash)`` for a new chained GuardAuditEvent.

    Takes the per-workspace chain lock (held until the caller's transaction
    ends). The verifier walks rows in (ts, id) order, so ``ts`` is stamped after
    the lock and never earlier than the current tail (instances' clocks can
    differ by a few ms). Use the returned ``ts`` and ``previous_hash`` on the
    row, then call ``chain_seal`` (ORM rows) or ``chain_seal_values`` (raw
    INSERT) once every other field is final.
    """
    last, ts = _tail_ts(db, ws_uuid)
    return ts, (last.entry_hash if last else "")


def chain_seal_values(values: dict) -> str:
    """v2 entry_hash for a complete column->value mapping (the only hashing path)."""
    from app.modules.guard.audit_chain import HASH_VERSION, compute_v3

    return compute_v3({**values, "hash_version": HASH_VERSION})


def chain_seal(event: "GuardAuditEvent") -> "GuardAuditEvent":
    """Stamp ``hash_version`` and ``entry_hash`` on an ORM row. Call last, after all
    other fields (including ``previous_hash`` from ``chain_begin``) are final."""
    import uuid as _uuid
    from app.modules.guard.audit_chain import HASH_VERSION, HASHED_FIELDS

    # Python-side column defaults only materialise at flush; hash what will be stored.
    if event.id is None:
        event.id = _uuid.uuid4()
    if event.source is None:
        event.source = "hook"
    event.hash_version = HASH_VERSION
    event.entry_hash = chain_seal_values({name: getattr(event, name, None) for name in HASHED_FIELDS})
    return event


def chain_seal_stored_row(db, row_id) -> str:
    """Seal a row that already exists in this transaction (two-phase gateway rows).

    The caller must hold the chain lock (``chain_begin`` earlier in the same
    transaction) and have already written ``ts``, ``previous_hash`` and
    ``hash_version`` on the row together with its final field values. The hash is
    computed from the columns as the database stores them, so it equals what the
    verifier and the export read back. Returns the entry hash.
    """
    from app.modules.guard.audit_chain import HASHED_FIELDS

    db.flush()
    row = db.query(GuardAuditEvent).filter(GuardAuditEvent.id == row_id).populate_existing().one()
    row.entry_hash = chain_seal_values({name: getattr(row, name, None) for name in HASHED_FIELDS})
    db.flush()
    return row.entry_hash
