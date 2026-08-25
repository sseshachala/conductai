"""feat(guard): conduct-base v2.15.0 — self-dogfood our own token shapes

Adds two agent-persona block rules to conduct-base so existing workspaces
pick them up on the next `conduct guard sync`:

  - no-conduct-tokens   cond_(agt|run|cred|live|api)_[a-f0-9]{32,}
  - no-booster-secrets  BOOSTER_SECRET["'\s:=]+[a-f0-9]{40,}

Motivated by a 2026-08-24 incident where a live cond_agt_ token was
echoed into a shell via a bad ${VAR:-DEFAULT} substitution and no active
rule caught it. Source of truth is the pack JSON at
apps/api/app/modules/guard/skill_packs/conduct-base.json — this migration
keeps every existing conduct-base version row + workspace policy cache
in sync.

Revision ID: 0097
Revises: 0096
Create Date: 2026-08-24
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None


_NEW_RULES = [
    {
        "id": "no-conduct-tokens",
        "persona": "agent",
        "non_overridable": True,
        "description": "Block Conduct-issued tokens (cond_agt_*, cond_run_*, cond_cred_*, cond_live_*, cond_api_*) from appearing in tool inputs or outputs",
        "match_pattern": r"cond_(agt|run|cred|live|api)_[a-f0-9]{32,}",
        "action": "block",
        "message": "Conduct token detected. Do not print, log, or commit Conduct tokens — rotate immediately and use a secrets manager.",
        "severity": "high",
        "frameworks": ["OWASP:A02", "SOC2:CC6.1"],
        "tag": "security_policy",
        "enforcement": {
            "version": 1,
            "proxy": "not_supported",
            "hook": "conditional",
            "mcp": "conditional",
            "runtime": "conditional",
            "guarantee": "Blocks the matching action only on surfaces marked hard or conditional when their listed dependencies are satisfied.",
            "requires": [
                "A supported pre-tool hook is installed, synced, and invoked before the action",
                "The agent invokes MCP guard_check with accurate tool_name and tool_input before acting",
                "Conduct workflow runtime Guard is enabled and matching content is present in workflow state",
            ],
            "known_limitations": [
                "Hook enforcement depends on the AI tool emitting supported structured hook events",
                "MCP cannot enforce actions the agent does not submit to guard_check",
                "Runtime evaluates serialized workflow state, not every external tool or model interaction",
            ],
        },
    },
    {
        "id": "no-booster-secrets",
        "persona": "agent",
        "non_overridable": True,
        "description": "Block Agent Booster secret values (BOOSTER_SECRET followed by a 40+ hex value, typically in .mcp.json env blocks)",
        "match_pattern": r"BOOSTER_SECRET[\"'\s:=]+[a-f0-9]{40,}",
        "action": "block",
        "message": "BOOSTER_SECRET value detected. Rotate the booster credential and use a secrets manager, not a plaintext .mcp.json.",
        "severity": "high",
        "frameworks": ["OWASP:A02", "SOC2:CC6.1"],
        "tag": "security_policy",
        "enforcement": {
            "version": 1,
            "proxy": "not_supported",
            "hook": "conditional",
            "mcp": "conditional",
            "runtime": "conditional",
            "guarantee": "Blocks the matching action only on surfaces marked hard or conditional when their listed dependencies are satisfied.",
            "requires": [
                "A supported pre-tool hook is installed, synced, and invoked before the action",
                "The agent invokes MCP guard_check with accurate tool_name and tool_input before acting",
                "Conduct workflow runtime Guard is enabled and matching content is present in workflow state",
            ],
            "known_limitations": [
                "Hook enforcement depends on the AI tool emitting supported structured hook events",
                "MCP cannot enforce actions the agent does not submit to guard_check",
                "Runtime evaluates serialized workflow state, not every external tool or model interaction",
            ],
        },
    },
]

_NEW_RULE_IDS = [r["id"] for r in _NEW_RULES]


def _append_rules(conn) -> None:
    """Append the new rules to every existing conduct-base version row
    (skip rows that already include the id, so re-runs are idempotent),
    then publish a v2.15.0 row and invalidate the policy cache."""
    for rule in _NEW_RULES:
        conn.execute(
            sa.text(
                """
                UPDATE skill_packs
                   SET rules = rules || CAST(:rule AS jsonb)
                 WHERE slug = 'conduct-base'
                   AND NOT (rules @> CAST(:probe AS jsonb))
                """
            ),
            {"rule": json.dumps(rule), "probe": json.dumps([{"id": rule["id"]}])},
        )

    conn.execute(
        sa.text(
            """
            INSERT INTO skill_packs (slug, version, name, tier, description, rules)
            SELECT 'conduct-base', '2.15.0', name, tier, description, rules
              FROM skill_packs
             WHERE slug = 'conduct-base'
             ORDER BY published_at DESC NULLS LAST, version DESC
             LIMIT 1
            ON CONFLICT (slug, version) DO UPDATE SET rules = EXCLUDED.rules
            """
        )
    )
    conn.execute(sa.text("DELETE FROM guard_policy_cache"))


def _strip_rules(conn) -> None:
    for rid in _NEW_RULE_IDS:
        conn.execute(
            sa.text(
                """
                UPDATE skill_packs
                   SET rules = (
                     SELECT COALESCE(jsonb_agg(r), '[]'::jsonb)
                       FROM jsonb_array_elements(rules) r
                      WHERE r->>'id' <> :rid
                   )
                 WHERE slug = 'conduct-base'
                """
            ),
            {"rid": rid},
        )
    conn.execute(
        sa.text("DELETE FROM skill_packs WHERE slug = 'conduct-base' AND version = '2.15.0'")
    )
    conn.execute(sa.text("DELETE FROM guard_policy_cache"))


def upgrade() -> None:
    _append_rules(op.get_bind())


def downgrade() -> None:
    _strip_rules(op.get_bind())
