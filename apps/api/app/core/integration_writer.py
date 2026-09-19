"""Single write path for ``Integration.encrypted_credentials``.

Every writer that touches a credential's ciphertext MUST go through
this module so ``integrations.revision`` stays authoritative and
concurrent updates never silently overwrite each other.

Two entry points:

- ``conditional_update(...)`` / ``conditional_delete(...)`` — SQL-level:
  execute an UPDATE/DELETE with a ``revision = :expected`` predicate and
  return the rowcount. Used by callers that already hold an expected
  revision (the env-vars editor). A rowcount of 0 means the row moved
  on and the caller must decide whether to refetch, remerge, or 409.

- ``merge_and_write(db, integration_id, merge_fn)`` — read/merge/write
  loop that uses ``conditional_update`` under the hood and refetches on
  contention. Used by every server-side rotation (gateway push, MCP
  push, agent identity provisioning, okta sync) so two racing writers
  don't lose each other's fields.

No other code path is allowed to touch
``Integration.encrypted_credentials``. Direct ORM assignment silently
skips revision, which is what the reviewer's P1-2 flagged.
"""
from __future__ import annotations

from sqlalchemy import delete as _delete, update as _update
from sqlalchemy.orm import Session

from app.models.integration import Integration


class IntegrationWriteExhausted(RuntimeError):
    """Raised when merge_and_write can't win the race after max_retries."""


def merge_and_write(
    db: Session,
    integration_id,
    merge_fn,
    *,
    max_retries: int = 5,
) -> None:
    """Read → decrypt → merge_fn(prev) → encrypt → conditional UPDATE.

    Retries on stale revision by refetching the row and running the merge
    against the newer state. Prevents lost updates when two rotation-style
    writers (gateway push, okta sync, identity provisioning, proxy config)
    race for the same row.

    ``merge_fn(prev_dict) -> new_dict`` — receives the current decrypted
    credentials (empty dict if the row has none) and returns the desired
    new state. Called once per attempt so a retry sees the latest state.
    """
    from app.core.crypto import decrypt as _decrypt, encrypt as _encrypt

    last_seen_revision: int | None = None
    for _ in range(max_retries):
        row = db.query(Integration).filter(Integration.id == integration_id).first()
        if row is None:
            raise IntegrationWriteExhausted(
                f"Integration {integration_id} disappeared during merge_and_write"
            )
        prev = _decrypt(row.encrypted_credentials) if row.encrypted_credentials else {}
        new_state = merge_fn(dict(prev))
        new_ct = _encrypt(new_state) if new_state else None
        rowcount = conditional_update(
            db,
            row.id,
            expected_revision=int(row.revision),
            new_ciphertext=new_ct,
        )
        if rowcount == 1:
            return
        last_seen_revision = int(row.revision)
        db.expire(row)
    raise IntegrationWriteExhausted(
        f"Integration {integration_id} still contended after {max_retries} retries "
        f"(last observed revision {last_seen_revision})"
    )


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
