"""
Seed the Autopilot workflow — watches for GitHub issues labeled 'autopilot ready',
implements the fix, runs tests, and opens a PR.

Run with: docker compose exec api python seed_autopilot.py
"""
import json
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.database_url)

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
WORKFLOW_ID   = "00000000-0000-0000-0000-000000000003"


def pos(col, row):
    return {"x": 80 + col * 260, "y": 80 + row * 180}


nodes = [
    {
        "id": "a1", "type": "block", "position": pos(0, 0),
        "data": {
            "type": "trigger",
            "label": "Issue labeled",
            "description": "GitHub issue labeled 'autopilot ready'",
            "integration": "github",
            "config": {
                "event_type": "github_issue",
                "label": "autopilot ready",
            },
        },
    },
    {
        "id": "a2", "type": "block", "position": pos(1, 0),
        "data": {
            "type": "tool",
            "label": "Fetch issue",
            "description": "Get full issue title, body, and metadata",
            "integration": "github",
            "config": {
                "action": "fetch_issue",
                "params": {
                    "owner": "{{a1.github_issue.repo_owner}}",
                    "repo": "{{a1.github_issue.repo_name}}",
                    "issue_number": "{{a1.github_issue.issue_number}}",
                },
            },
        },
    },
    {
        "id": "a3", "type": "block", "position": pos(2, 0),
        "data": {
            "type": "brain",
            "label": "Implement fix",
            "isAgentic": True,
            "description": (
                "You are an expert software engineer. "
                "A GitHub issue has been labeled 'autopilot ready'.\n\n"
                "Issue title: {{a2.title}}\n"
                "Issue body: {{a2.body}}\n"
                "Repo: {{a1.github_issue.repo_full_name}}\n"
                "Clone URL: {{a1.github_issue.clone_url}}\n\n"
                "Steps:\n"
                "1. Clone the repo: git clone <clone_url> /tmp/autopilot_repo\n"
                "2. Create a branch: git checkout -b autopilot/issue-{{a2.issue_number}}\n"
                "3. Read relevant files to understand the codebase\n"
                "4. Implement the fix described in the issue\n"
                "5. Stage changes: git add -A\n"
                "6. Commit: git commit -m 'fix: <short description> (closes #{{a2.issue_number}})'\n"
                "7. Output the branch name and a brief summary of what you changed"
            ),
        },
    },
    {
        "id": "a4", "type": "block", "position": pos(3, 0),
        "data": {
            "type": "brain",
            "label": "Run tests",
            "isAgentic": True,
            "description": (
                "Run the test suite for the repo at /tmp/autopilot_repo.\n"
                "1. Detect the test runner (pytest, npm test, etc.) by reading package.json or requirements.txt\n"
                "2. Run the tests\n"
                "3. Output: {passed: true/false, output: <test output summary>}"
            ),
        },
    },
    {
        "id": "a5", "type": "block", "position": pos(2, 1),
        "data": {
            "type": "logic",
            "label": "Tests pass?",
            "description": "Branch on whether tests passed. Check a4.passed == true",
        },
    },
    {
        "id": "a6", "type": "block", "position": pos(1, 2),
        "data": {
            "type": "brain",
            "label": "Fix failures",
            "isAgentic": True,
            "description": (
                "Tests failed. Output from test run:\n{{a4.output}}\n\n"
                "Read the failing test output, identify the root cause, patch the code, "
                "re-run tests. Max 3 attempts. "
                "If still failing after 3 attempts, output {passed: false, gave_up: true}."
            ),
        },
    },
    {
        "id": "a7", "type": "block", "position": pos(3, 1),
        "data": {
            "type": "brain",
            "label": "Push & open PR",
            "isAgentic": True,
            "description": (
                "Push the branch and open a pull request.\n"
                "Repo: {{a1.github_issue.repo_full_name}}\n"
                "Branch: autopilot/issue-{{a2.issue_number}}\n"
                "Base: {{a1.github_issue.default_branch}}\n\n"
                "1. cd /tmp/autopilot_repo\n"
                "2. git push origin autopilot/issue-{{a2.issue_number}}\n"
                "   (Use the GitHub token from credentials — set it via: "
                "git remote set-url origin https://<token>@github.com/{{a1.github_issue.repo_full_name}}.git)\n"
                "3. Use the GitHub API to open a pull request:\n"
                "   POST https://api.github.com/repos/{{a1.github_issue.repo_full_name}}/pulls\n"
                "   {title: 'fix: {{a2.title}} (closes #{{a2.issue_number}})', "
                "head: 'autopilot/issue-{{a2.issue_number}}', "
                "base: '{{a1.github_issue.default_branch}}', "
                "body: 'Automated fix by Delegator.\n\nCloses #{{a2.issue_number}}'}\n"
                "4. Output the PR URL"
            ),
        },
    },
    {
        "id": "a8", "type": "block", "position": pos(3, 2),
        "data": {
            "type": "output",
            "label": "Notify PR ready",
            "description": "PR opened for issue #{{a2.issue_number}}: {{a2.title}}. Review at {{a7.pr_url}}",
            "integration": "slack",
            "config": {
                "integration": "slack",
                "channel": "#engineering",
            },
        },
    },
]

edges = [
    {"id": "e1-2", "source": "a1", "target": "a2"},
    {"id": "e2-3", "source": "a2", "target": "a3"},
    {"id": "e3-4", "source": "a3", "target": "a4"},
    {"id": "e4-5", "source": "a4", "target": "a5"},
    {"id": "e5-6", "source": "a5", "target": "a6", "sourceHandle": "fail"},
    {"id": "e6-4", "source": "a6", "target": "a4"},
    {"id": "e5-7", "source": "a5", "target": "a7", "sourceHandle": "pass"},
    {"id": "e7-8", "source": "a7", "target": "a8"},
]

graph = {"nodes": nodes, "edges": edges}

with engine.connect() as conn:
    result = conn.execute(text("SELECT id FROM workflows WHERE name = 'Autopilot — GitHub Issues' LIMIT 1"))
    if result.fetchone():
        print("Already seeded — skipping.")
    else:
        conn.execute(text("""
            INSERT INTO workflows (id, workspace_id, name, default_mode)
            VALUES (:wf_id, :ws_id, 'Autopilot — GitHub Issues', 'dag')
        """), {"wf_id": WORKFLOW_ID, "ws_id": WORKSPACE_ID})

        version_id = conn.execute(text("""
            INSERT INTO workflow_versions (workflow_id, graph)
            VALUES (:wf_id, cast(:graph as jsonb))
            RETURNING id
        """), {"wf_id": WORKFLOW_ID, "graph": json.dumps(graph)}).fetchone()[0]

        conn.execute(text("""
            UPDATE workflows SET current_version_id = :vid WHERE id = :wf_id
        """), {"vid": str(version_id), "wf_id": WORKFLOW_ID})

        conn.commit()
        print(f"Seeded 'Autopilot — GitHub Issues' — {len(nodes)} blocks, {len(edges)} edges.")
        print(f"Workflow ID: {WORKFLOW_ID}")
