"""add owner_id to workspaces and project_templates table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-08
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
import json

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Template graph data
# ---------------------------------------------------------------------------

def _pos(col, row):
    return {"x": 80 + col * 260, "y": 80 + row * 180}


_AUTOPILOT_NODES = [
    {"id": "a1", "type": "block", "position": _pos(0, 0), "data": {"type": "trigger", "label": "Issue labeled", "description": "GitHub issue labeled 'autopilot ready'", "integration": "github", "config": {"event_type": "github_issue", "label": "autopilot ready"}}},
    {"id": "a2", "type": "block", "position": _pos(1, 0), "data": {"type": "tool", "label": "Fetch issue", "description": "Get full issue title, body, and metadata", "integration": "github", "config": {"action": "fetch_issue", "params": {"owner": "{{a1.github_issue.repo_owner}}", "repo": "{{a1.github_issue.repo_name}}", "issue_number": "{{a1.github_issue.issue_number}}"}}}},
    {"id": "a3", "type": "block", "position": _pos(2, 0), "data": {"type": "brain", "label": "Implement fix", "isAgentic": True, "description": "You are an expert software engineer. A GitHub issue has been labeled 'autopilot ready'.\n\nIssue title: {{a2.title}}\nIssue body: {{a2.body}}\nRepo: {{a1.github_issue.repo_full_name}}\nClone URL: {{a1.github_issue.clone_url}}\n\nSteps:\n1. Clone the repo: git clone <clone_url> /tmp/autopilot_repo\n2. Create a branch: git checkout -b autopilot/issue-{{a2.issue_number}}\n3. Read relevant files to understand the codebase\n4. Implement the fix described in the issue\n5. Stage changes: git add -A\n6. Commit: git commit -m 'fix: <short description> (closes #{{a2.issue_number}})'\n7. Output the branch name and a brief summary of what you changed"}},
    {"id": "a4", "type": "block", "position": _pos(3, 0), "data": {"type": "brain", "label": "Run tests & fix", "isAgentic": True, "description": "Run the test suite for the repo at /tmp/autopilot_repo. If tests fail, fix the failures and re-run. Repeat up to 3 times.\n\n1. Detect the test runner (pytest, npm test, etc.) by reading package.json or requirements.txt\n2. Run the tests\n3. If tests fail: read the failure output, patch the code, re-run\n4. After up to 3 fix attempts, stop regardless of outcome\n\nOutput as JSON on the final line:\n{\"passed\": true/false, \"attempts\": <number>, \"output\": \"<brief summary of test results>\"}"}},
    {"id": "a5", "type": "block", "position": _pos(3, 1), "data": {"type": "logic", "label": "Tests pass?", "description": "Branch on whether tests passed. Check a4.passed == true"}},
    {"id": "a6", "type": "block", "position": _pos(4, 0), "data": {"type": "brain", "label": "Push & open PR", "isAgentic": True, "description": "Push the branch and open a pull request.\nRepo: {{a1.github_issue.repo_full_name}}\nBranch: autopilot/issue-{{a2.issue_number}}\nBase: {{a1.github_issue.default_branch}}\n\n1. cd /tmp/autopilot_repo\n2. Set the remote with credentials:\n   git remote set-url origin https://<github_token>@github.com/{{a1.github_issue.repo_full_name}}.git\n3. git push origin autopilot/issue-{{a2.issue_number}}\n4. Open a PR via the GitHub API\n\nOutput ONLY the following JSON on the last line of your response:\n{\"pr_url\": \"<full PR URL>\"}"}},
    {"id": "a7", "type": "block", "position": _pos(4, 1), "data": {"type": "output", "label": "Notify PR ready", "description": "PR opened for issue #{{a2.issue_number}}: {{a2.title}}. Review at {{a6.pr_url}}", "integration": "slack", "config": {"integration": "slack", "channel": "#engineering"}}},
    {"id": "a8", "type": "block", "position": _pos(2, 2), "data": {"type": "output", "label": "Notify failure", "description": "Tests failed after {{a4.attempts}} attempt(s) for issue #{{a2.issue_number}}: {{a2.title}}. Manual review needed.", "integration": "slack", "config": {"integration": "slack", "channel": "#engineering"}}},
]
_AUTOPILOT_EDGES = [
    {"id": "e1-2", "source": "a1", "target": "a2"},
    {"id": "e2-3", "source": "a2", "target": "a3"},
    {"id": "e3-4", "source": "a3", "target": "a4"},
    {"id": "e4-5", "source": "a4", "target": "a5"},
    {"id": "e5-6", "source": "a5", "target": "a6", "sourceHandle": "pass"},
    {"id": "e6-7", "source": "a6", "target": "a7"},
    {"id": "e5-8", "source": "a5", "target": "a8", "sourceHandle": "fail"},
]

def _pos2(col, row):
    return {"x": 60 + col * 200, "y": 60 + row * 160}

_STORY_PR_NODES = [
    {"id": "b1",  "type": "block", "position": _pos2(0, 0), "data": {"type": "trigger",  "label": "Story ready",       "description": "Linear webhook when label = ai-ready", "integration": "linear"}},
    {"id": "b2",  "type": "block", "position": _pos2(1, 0), "data": {"type": "tool",     "label": "Fetch story",        "description": "Pull title, description, criteria",    "integration": "linear"}},
    {"id": "b3",  "type": "block", "position": _pos2(2, 0), "data": {"type": "output",   "label": "Slack: starting",    "description": "Post 'working on STORY-X'",            "integration": "slack"}},
    {"id": "b4",  "type": "block", "position": _pos2(3, 0), "data": {"type": "tool",     "label": "Provision sandbox",  "description": "Spin up Ubuntu droplet",               "integration": "digitalocean"}},
    {"id": "b5",  "type": "block", "position": _pos2(0, 1), "data": {"type": "tool",     "label": "Checkout",           "description": "Clone repo, create feat/STORY-X branch","integration": "github"}},
    {"id": "b6",  "type": "block", "position": _pos2(1, 1), "data": {"type": "brain",    "label": "Generate code",      "description": "Implement story with file/shell tools", "isAgentic": True}},
    {"id": "b7",  "type": "block", "position": _pos2(2, 1), "data": {"type": "tool",     "label": "Run tests",          "description": "Execute unit + smoke suites"}},
    {"id": "b8",  "type": "block", "position": _pos2(3, 1), "data": {"type": "logic",    "label": "Pass or fail?",      "description": "Branch on test exit code"}},
    {"id": "b9",  "type": "block", "position": _pos2(0, 2), "data": {"type": "brain",    "label": "Fix loop",           "description": "Read failures, patch — max 3 tries",   "isAgentic": True}},
    {"id": "b10", "type": "block", "position": _pos2(1, 2), "data": {"type": "tool",     "label": "Push + draft PR",    "description": "Push branch, open draft PR",           "integration": "github"}},
    {"id": "b11", "type": "block", "position": _pos2(2, 2), "data": {"type": "tool",     "label": "Wait for preview",   "description": "Poll until Vercel deploy is READY",    "integration": "vercel"}},
    {"id": "b12", "type": "block", "position": _pos2(3, 2), "data": {"type": "approval", "label": "Await reviewer",     "description": "DM with PR + preview link, pause until ✓", "integration": "slack"}},
    {"id": "b13", "type": "block", "position": _pos2(1, 3), "data": {"type": "tool",     "label": "Merge to main",      "description": "Squash-merge on approval",             "integration": "github"}},
    {"id": "b14", "type": "block", "position": _pos2(2, 3), "data": {"type": "tool",     "label": "Wait for prod",      "description": "Poll until production deploy is READY","integration": "vercel"}},
    {"id": "b15", "type": "block", "position": _pos2(3, 3), "data": {"type": "output",   "label": "Notify shipped",     "description": "Post confirmation with prod URL",       "integration": "slack"}},
    {"id": "b16", "type": "block", "position": _pos2(0, 3), "data": {"type": "cleanup",  "label": "Tear down",          "description": "Destroy droplet — always runs",        "integration": "digitalocean"}},
]
_STORY_PR_EDGES = [
    {"id": "e1-2",   "source": "b1",  "target": "b2"},
    {"id": "e2-3",   "source": "b2",  "target": "b3"},
    {"id": "e3-4",   "source": "b3",  "target": "b4"},
    {"id": "e4-5",   "source": "b4",  "target": "b5"},
    {"id": "e5-6",   "source": "b5",  "target": "b6"},
    {"id": "e6-7",   "source": "b6",  "target": "b7"},
    {"id": "e7-8",   "source": "b7",  "target": "b8"},
    {"id": "e8-9",   "source": "b8",  "target": "b9",  "label": "fail"},
    {"id": "e9-7",   "source": "b9",  "target": "b7",  "label": "retry"},
    {"id": "e8-10",  "source": "b8",  "target": "b10", "label": "pass"},
    {"id": "e10-11", "source": "b10", "target": "b11"},
    {"id": "e11-12", "source": "b11", "target": "b12"},
    {"id": "e12-13", "source": "b12", "target": "b13"},
    {"id": "e13-14", "source": "b13", "target": "b14"},
    {"id": "e14-15", "source": "b14", "target": "b15"},
    {"id": "e15-16", "source": "b15", "target": "b16"},
]

_TEMPLATES = [
    {
        "id": "00000000-0000-0000-0000-000000000010",
        "slug": "autopilot",
        "name": "Autopilot — GitHub Issues",
        "description": "Watches for issues labeled 'autopilot ready', writes the fix, runs tests, and opens a PR.",
        "default_mode": "dag",
        "nodes": json.dumps(_AUTOPILOT_NODES),
        "edges": json.dumps(_AUTOPILOT_EDGES),
    },
    {
        "id": "00000000-0000-0000-0000-000000000011",
        "slug": "story-pr",
        "name": "Story → PR",
        "description": "Linear ticket labeled ai-ready triggers code generation, test run, Vercel preview, and human approval before merge.",
        "default_mode": "dag",
        "nodes": json.dumps(_STORY_PR_NODES),
        "edges": json.dumps(_STORY_PR_EDGES),
    },
]


def upgrade() -> None:
    # Add owner_id to workspaces (nullable — existing rows get NULL / 'dev')
    op.add_column("workspaces", sa.Column("owner_id", sa.String(255), nullable=True))
    op.execute("UPDATE workspaces SET owner_id = 'dev' WHERE id = '00000000-0000-0000-0000-000000000001'")

    op.create_table(
        "project_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("default_mode", sa.String(50), nullable=False, server_default="dag"),
        sa.Column("nodes", JSONB, nullable=False, server_default="[]"),
        sa.Column("edges", JSONB, nullable=False, server_default="[]"),
    )

    for t in _TEMPLATES:
        op.execute(sa.text(
            "INSERT INTO project_templates (id, slug, name, description, default_mode, nodes, edges) "
            "VALUES (:id, :slug, :name, :description, :default_mode, cast(:nodes as jsonb), cast(:edges as jsonb))"
        ).bindparams(**t))


def downgrade() -> None:
    op.drop_table("project_templates")
    op.drop_column("workspaces", "owner_id")
