"""
Seed the Autopilot workflow — watches for GitHub issues labeled 'autopilot ready',
implements the fix, runs tests (with inline retry), and opens a PR.

Run with: docker compose exec api python seed_autopilot.py

Graph: a1 → a2 → a3 → a4 → a5 → a6 → a7
  a1: Trigger (github issue labeled)
  a2: Fetch issue (tool block)
  a3: Implement fix (Brain)
  a4: Run tests + fix failures (Brain — handles retry internally, no DAG cycle)
  a5: Logic — did tests pass?
  a6: Push & open PR (Brain) — pass path
  a7: Notify PR ready (output/slack)
  a8: Notify failure (output/slack) — fail path from a5
"""
import json
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.database_url)

# dev workspace only — do not run against production
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
                "event_type": "github_issue_labeled",
                "label_mode": "one_of",
                "labels": "autopilot ready,ai_ready",
                "enforcement": "strict",
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
            "label": "Run tests & fix",
            "isAgentic": True,
            "description": (
                "Run the test suite for the repo at /tmp/autopilot_repo. "
                "If tests fail, fix the failures and re-run. Repeat up to 3 times.\n\n"
                "1. Detect the test runner (pytest, npm test, etc.) by reading "
                "package.json or requirements.txt\n"
                "2. Run the tests\n"
                "3. If tests fail: read the failure output, patch the code, re-run\n"
                "4. After up to 3 fix attempts, stop regardless of outcome\n\n"
                "Output as JSON on the final line:\n"
                '{"passed": true/false, "attempts": <number>, '
                '"output": "<brief summary of test results>"}'
            ),
        },
    },
    {
        "id": "a5", "type": "block", "position": pos(3, 1),
        "data": {
            "type": "logic",
            "label": "Tests pass?",
            "description": "Branch on whether tests passed",
            "config": {"condition": "passed == true"},
        },
    },
    {
        "id": "a6", "type": "block", "position": pos(4, 0),
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
                "2. Set the remote with credentials:\n"
                "   git remote set-url origin "
                "https://<github_token>@github.com/{{a1.github_issue.repo_full_name}}.git\n"
                "   (retrieve the GitHub token from the Delegator credentials vault)\n"
                "3. git push origin autopilot/issue-{{a2.issue_number}}\n"
                "4. Open a PR via the GitHub API:\n"
                "   POST https://api.github.com/repos/{{a1.github_issue.repo_full_name}}/pulls\n"
                '   {"title": "fix: {{a2.title}} (closes #{{a2.issue_number}})", '
                '"head": "autopilot/issue-{{a2.issue_number}}", '
                '"base": "{{a1.github_issue.default_branch}}", '
                '"body": "Automated fix by Delegator.\\n\\nCloses #{{a2.issue_number}}"}\n\n'
                "Output ONLY the following JSON on the last line of your response:\n"
                '{"pr_url": "<full PR URL>"}'
            ),
        },
    },
    {
        "id": "a7", "type": "block", "position": pos(4, 1),
        "data": {
            "type": "output",
            "label": "Notify PR ready",
            "description": "PR opened for issue #{{a2.issue_number}}: {{a2.title}}. Review at {{a6.pr_url}}",
            "integration": "slack",
            "config": {
                "integration": "slack",
                "channel": "#engineering",
            },
        },
    },
    {
        "id": "a8", "type": "block", "position": pos(2, 2),
        "data": {
            "type": "output",
            "label": "Notify failure",
            "description": (
                "Tests failed after {{a4.attempts}} attempt(s) for issue "
                "#{{a2.issue_number}}: {{a2.title}}. Manual review needed."
            ),
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
    {"id": "e5-6", "source": "a5", "target": "a6", "sourceHandle": "pass"},
    {"id": "e6-7", "source": "a6", "target": "a7"},
    {"id": "e5-8", "source": "a5", "target": "a8", "sourceHandle": "fail"},
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
