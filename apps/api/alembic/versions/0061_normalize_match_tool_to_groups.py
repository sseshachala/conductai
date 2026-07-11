"""normalize match_tool values to semantic group names

Revision ID: 0061
Revises: 0060
Create Date: 2026-07-11
"""
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

# Raw tool name → semantic group
_RAW_TO_GROUP = {
    "bash": "shell", "run_command": "shell", "execute": "shell",
    "terminal": "shell",
    "write": "filesystem-write", "edit": "filesystem-write",
    "write_file": "filesystem-write", "edit_file": "filesystem-write",
    "str_replace_editor": "filesystem-write",
    "read": "filesystem-read", "read_file": "filesystem-read",
    "glob": "filesystem-read", "grep": "filesystem-read",
    "list_directory": "filesystem-read",
    "web_fetch": "network", "web_search": "network",
    "http_request": "network", "curl": "network", "fetch": "network",
}


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(
        "SELECT id, match_tool FROM guard_policies WHERE match_tool IS NOT NULL AND match_tool != '*'"
    ).fetchall()
    for row_id, match_tool in rows:
        tokens = [t.strip().lower() for t in match_tool.split(",") if t.strip()]
        groups: list[str] = []
        for token in tokens:
            g = _RAW_TO_GROUP.get(token, token)
            if g not in groups:
                groups.append(g)
        new_val = ",".join(groups)
        if new_val != match_tool:
            conn.execute(
                "UPDATE guard_policies SET match_tool = %s WHERE id = %s",
                (new_val, row_id),
            )


def downgrade():
    pass  # one-way migration — raw names are gone
