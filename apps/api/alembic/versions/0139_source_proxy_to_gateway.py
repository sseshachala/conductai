"""Rename audit source value 'proxy' -> 'gateway'.

The audit ``source`` column ('hook' | 'proxy' | 'mcp' | 'workflow') was
labeled 'proxy' back when the LLM path lived under ``/proxy/*``. After
PR #2066 the canonical URL is ``/gateway/v1/*`` and the isolated
service is ``gateway.conductai.ai`` — the audit label lagged behind.

This migration:
  1. Rewrites historical rows: ``source='proxy'`` -> ``source='gateway'``.
  2. Paired writer changes in the same PR stamp ``'gateway'`` on new rows,
     so from this point on the label matches the URL.

**Safety:** the audit hash chain input is
``ts | tool_call | decision | prev_hash`` (see events.py:1447). The
``source`` column is NOT part of that hash, so this UPDATE cannot
invalidate any previously computed ``entry_hash``. Verification will
still pass on rewritten rows.

**Sizing:** if ``guard_audit_events`` has >5M rows, this UPDATE may hold
locks long enough to matter. Replace with a batched form (LIMIT +
loop) if PR-0.6 counts show it.

**GuardInbox:** the ``guard_inbox`` table is populated by an AFTER
INSERT trigger on ``guard_audit_events`` (migration 0122). This
migration issues UPDATE, not INSERT, so the trigger does not re-fire.
Historical inbox rows keep ``source='proxy'`` and their existing
``dedup_key`` (which incorporates 'proxy'). New audit events will land
with ``source='gateway'`` and produce new inbox rows under a new
dedup_key. The inbox router Literal has been widened to accept both
values for filter compatibility.

Re-computing historical inbox rows' ``source`` + ``dedup_key`` is a
separate concern (PR-0.7b): it requires re-hashing to match the
trigger formula and could collide with any 'gateway'-labeled inbox
rows that appear between this migration and the followup. Deferred
until we have a clear need.
"""
from alembic import op


revision = "0139"
down_revision = "0138"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE guard_audit_events SET source = 'gateway' WHERE source = 'proxy'")


def downgrade() -> None:
    op.execute("UPDATE guard_audit_events SET source = 'proxy' WHERE source = 'gateway'")
