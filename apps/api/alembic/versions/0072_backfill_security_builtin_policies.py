"""backfill builtin security policies for existing workspaces

Revision ID: 0072
Revises: 0071
Create Date: 2026-06-09
"""
from __future__ import annotations

import uuid
from pathlib import Path

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None

_YAML_PATH = Path(__file__).parent.parent.parent / "app" / "modules" / "security" / "builtin_policies.yaml"


def upgrade() -> None:
    import yaml

    try:
        with open(_YAML_PATH) as f:
            policies = yaml.safe_load(f) or []
    except Exception as e:
        print(f"[0072] WARNING: could not load builtin_policies.yaml: {e}")
        return

    bind = op.get_bind()
    session = Session(bind=bind)

    # All workspaces with Security module installed
    rows = session.execute(
        sa.text("SELECT workspace_id FROM security_config WHERE installed = TRUE")
    ).fetchall()

    if not rows:
        print("[0072] No installed Security workspaces found — nothing to backfill.")
        return

    inserted = 0
    for (workspace_id,) in rows:
        ws_uuid = uuid.UUID(str(workspace_id))
        for policy in policies:
            rule_id = policy.get("rule_id")
            if not rule_id:
                continue
            existing = session.execute(
                sa.text(
                    "SELECT 1 FROM security_policies WHERE workspace_id = :ws AND rule_id = :rid"
                ),
                {"ws": str(ws_uuid), "rid": rule_id},
            ).first()
            if not existing:
                session.execute(
                    sa.text("""
                        INSERT INTO security_policies
                            (id, workspace_id, rule_id, description, pattern, finding_type, severity, enabled, builtin, created_at)
                        VALUES
                            (:id, :ws, :rid, :desc, :pat, :ftype, :sev, TRUE, TRUE, NOW())
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "ws": str(ws_uuid),
                        "rid": rule_id,
                        "desc": policy.get("description", ""),
                        "pat": policy.get("pattern"),
                        "ftype": policy.get("finding_type", "other"),
                        "sev": policy.get("severity", "medium"),
                    },
                )
                inserted += 1

    session.commit()
    print(f"[0072] Backfilled {inserted} policies across {len(rows)} workspace(s).")


def downgrade() -> None:
    # Remove policies that are builtin=True and were added after this migration
    # Safe: only removes builtin rows, custom policies are unaffected
    op.execute(
        "DELETE FROM security_policies WHERE builtin = TRUE AND rule_id IN ("
        "'secret-stripe','secret-slack','secret-private-key',"
        "'cmd-injection','sql-injection','weak-hash-md5','weak-hash-sha1'"
        ")"
    )
