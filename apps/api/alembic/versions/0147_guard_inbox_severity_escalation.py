"""guard_inbox: escalate severity when a grouped finding gets worse.

Revision ID: 0147
Revises: 0146
Create Date: 2026-09-21

The 0123 trigger function ``guard_inbox_populate()`` computes a severity
per-decision (blocked→critical, warned→medium, approved→low) on the INSERT
path but never touches ``severity`` in the ON CONFLICT branch. So a group
whose first fire is ``warned`` (severity=medium) that later re-fires as
``blocked`` (would map to critical) stays flagged medium. Triage misses
the actual escalation.

Fix: keep the current dedup + auto-reopen semantics exactly, add ordinal
severity max (critical > medium > low) inside the ON CONFLICT DO UPDATE.
Uses ``CREATE OR REPLACE FUNCTION`` — the existing INSERT trigger
(guard_inbox_populate_trg) and the UPDATE trigger from 0133
(guard_inbox_populate_upd_trg) reference the function by name and pick
up the new body without needing to be re-created. Downgrade restores the
0123 body verbatim.
"""
from __future__ import annotations

from alembic import op


# revision identifiers
revision = "0147"
down_revision = "0146"
branch_labels = None
depends_on = None


# Ordinal severity: critical=3, medium=2, low=1. Used inside a plain
# CASE-based max so the plpgsql body stays readable (no GREATEST across
# text values, no lookup table).
_UPGRADE_FN = """
CREATE OR REPLACE FUNCTION guard_inbox_populate() RETURNS TRIGGER AS $body$
DECLARE
    v_dedup TEXT;
    v_severity TEXT;
BEGIN
    IF NEW.decision NOT IN ('blocked', 'warned', 'approved') THEN
        RETURN NEW;
    END IF;

    IF NEW.rule_id IS NULL THEN
        RETURN NEW;
    END IF;

    v_dedup := encode(
        digest(
            NEW.workspace_id::text ||
            COALESCE(NEW.rule_id, '') ||
            COALESCE(NEW.source, '') ||
            LEFT(COALESCE(NEW.rule_message, ''), 200),
            'sha256'
        ),
        'hex'
    );

    v_severity := CASE NEW.decision
        WHEN 'blocked'  THEN 'critical'
        WHEN 'warned'   THEN 'medium'
        WHEN 'approved' THEN 'low'
    END;

    INSERT INTO guard_inbox (
        workspace_id, dedup_key, rule_id, source, severity,
        description, latest_event_id, first_seen_at, last_seen_at
    )
    VALUES (
        NEW.workspace_id, v_dedup, NEW.rule_id, NEW.source, v_severity,
        NEW.rule_message, NEW.id, NEW.ts, NEW.ts
    )
    ON CONFLICT (workspace_id, dedup_key) DO UPDATE
    SET occurrences     = guard_inbox.occurrences + 1,
        last_seen_at    = NEW.ts,
        latest_event_id = NEW.id,
        -- #2170-follow-up (Inbox correctness PR 1) — ordinal max so a
        -- warned → blocked sequence bumps severity from medium to critical.
        -- Vocabulary matches the router / UI accepted enum: critical,
        -- medium, low. Ranks anything unknown at 0 so it never wins.
        severity = CASE
            WHEN (CASE v_severity
                    WHEN 'critical' THEN 3
                    WHEN 'medium'   THEN 2
                    WHEN 'low'      THEN 1
                    ELSE 0
                  END)
              > (CASE guard_inbox.severity
                    WHEN 'critical' THEN 3
                    WHEN 'medium'   THEN 2
                    WHEN 'low'      THEN 1
                    ELSE 0
                  END)
            THEN v_severity
            ELSE guard_inbox.severity
        END,
        status          = CASE WHEN guard_inbox.status = 'resolved'
                               THEN 'open' ELSE guard_inbox.status END,
        resolved_reason = CASE WHEN guard_inbox.status = 'resolved'
                               THEN NULL ELSE guard_inbox.resolved_reason END,
        resolved_at     = CASE WHEN guard_inbox.status = 'resolved'
                               THEN NULL ELSE guard_inbox.resolved_at END,
        resolved_by     = CASE WHEN guard_inbox.status = 'resolved'
                               THEN NULL ELSE guard_inbox.resolved_by END,
        resolved_note   = CASE WHEN guard_inbox.status = 'resolved'
                               THEN NULL ELSE guard_inbox.resolved_note END;

    RETURN NEW;
END;
$body$ LANGUAGE plpgsql;
"""


# Verbatim body from migration 0123 — restore so downgrade returns the
# tree to its pre-0147 behavior (severity fixed at first fire).
_DOWNGRADE_FN = """
CREATE OR REPLACE FUNCTION guard_inbox_populate() RETURNS TRIGGER AS $body$
DECLARE
    v_dedup TEXT;
    v_severity TEXT;
BEGIN
    IF NEW.decision NOT IN ('blocked', 'warned', 'approved') THEN
        RETURN NEW;
    END IF;

    IF NEW.rule_id IS NULL THEN
        RETURN NEW;
    END IF;

    v_dedup := encode(
        digest(
            NEW.workspace_id::text ||
            COALESCE(NEW.rule_id, '') ||
            COALESCE(NEW.source, '') ||
            LEFT(COALESCE(NEW.rule_message, ''), 200),
            'sha256'
        ),
        'hex'
    );

    v_severity := CASE NEW.decision
        WHEN 'blocked'  THEN 'critical'
        WHEN 'warned'   THEN 'medium'
        WHEN 'approved' THEN 'low'
    END;

    INSERT INTO guard_inbox (
        workspace_id, dedup_key, rule_id, source, severity,
        description, latest_event_id, first_seen_at, last_seen_at
    )
    VALUES (
        NEW.workspace_id, v_dedup, NEW.rule_id, NEW.source, v_severity,
        NEW.rule_message, NEW.id, NEW.ts, NEW.ts
    )
    ON CONFLICT (workspace_id, dedup_key) DO UPDATE
    SET occurrences     = guard_inbox.occurrences + 1,
        last_seen_at    = NEW.ts,
        latest_event_id = NEW.id,
        status          = CASE WHEN guard_inbox.status = 'resolved'
                               THEN 'open' ELSE guard_inbox.status END,
        resolved_reason = CASE WHEN guard_inbox.status = 'resolved'
                               THEN NULL ELSE guard_inbox.resolved_reason END,
        resolved_at     = CASE WHEN guard_inbox.status = 'resolved'
                               THEN NULL ELSE guard_inbox.resolved_at END,
        resolved_by     = CASE WHEN guard_inbox.status = 'resolved'
                               THEN NULL ELSE guard_inbox.resolved_by END,
        resolved_note   = CASE WHEN guard_inbox.status = 'resolved'
                               THEN NULL ELSE guard_inbox.resolved_note END;

    RETURN NEW;
END;
$body$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_FN)


def downgrade() -> None:
    op.execute(_DOWNGRADE_FN)
