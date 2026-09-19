"""Single write path for ``Integration.encrypted_credentials``.

Every writer that touches a credential's ciphertext MUST go through
this module so ``integrations.revision`` stays authoritative and
concurrent updates never silently overwrite each other.

Two entry points:

- ``bump_encrypted(row, new_ciphertext)`` — ORM-flavored: mutates the
  loaded row and bumps its revision. Callers that don't need to guard
  against a concurrent writer (identity provisioning, gateway push,
  server-side rotations) use this. It always increments revision, which
  is what unblocks the editor-open-during-rotation race the reviewer
  flagged in P1-2.

- ``conditional_update(...)`` / ``conditional_delete(...)`` — SQL-level:
  execute an UPDATE/DELETE with a ``revision = :expected`` predicate and
  return the rowcount. Used by the env-vars editor path where a stale
  client must be told to reload instead of silently clobbering another
  editor's save.

The env-vars endpoints use the conditional variants for correctness under
contention; the other writers just bump so any editor holding an old
revision is refused on its next save. Both flows write through this
module — no other code path is allowed to touch
``Integration.encrypted_credentials`` without at least bumping revision.
"""
from __future__ import annotations

from sqlalchemy import delete as _delete, update as _update
from sqlalchemy.orm import Session

from app.models.integration import Integration


def bump_encrypted(row: Integration, new_ciphertext: str | None) -> None:
    """Set ciphertext and bump revision atomically at the ORM layer.

    Not race-safe against concurrent writers on the same row — it just
    guarantees the revision advances so the next editor save fails fast
    on its ``expected_revision`` check.
    """
    row.encrypted_credentials = new_ciphertext
    row.revision = int(row.revision or 1) + 1


def conditional_update(
    db: Session,
    integration_id,
    *,
    expected_revision: int,
    new_ciphertext: str | None,
) -> int:
    """Atomic conditional UPDATE. Returns rowcount.

    Rowcount of 0 means the row was already advanced by another writer;
    the caller must refetch to report ``current_revision`` in a 409.
    """
    result = db.execute(
        _update(Integration)
        .where(
            Integration.id == integration_id,
            Integration.revision == expected_revision,
        )
        .values(
            encrypted_credentials=new_ciphertext,
            revision=Integration.revision + 1,
        )
    )
    return int(result.rowcount or 0)


def conditional_delete(
    db: Session,
    integration_id,
    *,
    expected_revision: int,
) -> int:
    """Atomic conditional DELETE. Returns rowcount.

    Same 0-rowcount → stale semantics as ``conditional_update``.
    """
    result = db.execute(
        _delete(Integration).where(
            Integration.id == integration_id,
            Integration.revision == expected_revision,
        )
    )
    return int(result.rowcount or 0)
