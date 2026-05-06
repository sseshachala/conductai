"""
Seed the "Deploy Delegator" workflow — deploys delegator-backend and delegator-ui
to Railway. This is Delegator deploying itself (dogfood).

Workflow graph (no cycles — pure DAG):

  d1 (trigger: webhook deploy_delegator)
    → d2 (tool: list_environments)       — get environment_id
    → d3 (tool: trigger backend deploy)  — returns deployment_id
    → d4 (tool: trigger frontend deploy) — returns deployment_id
    → d5 (tool: wait for backend)        — polls until done, returns {healthy: bool}
    → d6 (tool: wait for frontend)       — polls until done, returns {healthy: bool}
    → d7 (logic: both healthy?)
    → d8 (output: notify success)        — pass branch
    → d9 (output: notify failure)        — fail branch

Artifact config is stored in each tool block's params — no separate DB table needed.
Service IDs are read from env vars at seed time; store them as PLACEHOLDER values
if you want to fill them in later via the workflow editor.

Run with: docker compose exec api python seed_deploy_delegator.py
"""
import json
import os
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.database_url)

# dev workspace — change to your workspace UUID in production
WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
WORKFLOW_ID  = "00000000-0000-0000-0000-000000000004"

# Read service IDs from env if set, otherwise use placeholder strings
# that can be filled in through the workflow editor.
RAILWAY_PROJECT_ID     = os.getenv("RAILWAY_PROJECT_ID", "REPLACE_WITH_RAILWAY_PROJECT_ID")
RAILWAY_BACKEND_SVC_ID = os.getenv("RAILWAY_BACKEND_SERVICE_ID", "REPLACE_WITH_BACKEND_SERVICE_ID")
RAILWAY_FRONTEND_SVC_ID = os.getenv("RAILWAY_FRONTEND_SERVICE_ID", "REPLACE_WITH_FRONTEND_SERVICE_ID")


def pos(col: int, row: int) -> dict:
    return {"x": 80 + col * 280, "y": 80 + row * 180}


nodes = [
    # ── Trigger ───────────────────────────────────────────────────────────────
    {
        "id": "d1", "type": "block", "position": pos(0, 1),
        "data": {
            "type": "trigger",
            "label": "Deploy triggered",
            "description": "Manual trigger or GitHub push to main branch",
            "integration": "railway",
            "config": {
                "event_type": "deploy_delegator",
            },
        },
    },

    # ── Get Railway environment ───────────────────────────────────────────────
    {
        "id": "d2", "type": "block", "position": pos(1, 1),
        "data": {
            "type": "tool",
            "label": "Get environment",
            "description": "Fetch the production environment ID from Railway",
            "integration": "railway",
            "config": {
                "action": "list_environments",
                "params": {
                    "project_id": RAILWAY_PROJECT_ID,
                },
            },
        },
    },

    # ── Artifact: delegator-backend ───────────────────────────────────────────
    {
        "id": "d3", "type": "block", "position": pos(2, 0),
        "data": {
            "type": "tool",
            "label": "Deploy backend",
            "description": "Trigger redeployment of delegator-backend on Railway",
            "integration": "railway",
            "config": {
                "action": "trigger_and_get_deployment",
                "params": {
                    "service_id": RAILWAY_BACKEND_SVC_ID,
                    "environment_id": "{{d2.environment_id}}",
                },
            },
        },
    },

    # ── Artifact: delegator-ui ────────────────────────────────────────────────
    {
        "id": "d4", "type": "block", "position": pos(2, 2),
        "data": {
            "type": "tool",
            "label": "Deploy frontend",
            "description": "Trigger redeployment of delegator-ui on Railway",
            "integration": "railway",
            "config": {
                "action": "trigger_and_get_deployment",
                "params": {
                    "service_id": RAILWAY_FRONTEND_SVC_ID,
                    "environment_id": "{{d2.environment_id}}",
                },
            },
        },
    },

    # ── Wait for backend ──────────────────────────────────────────────────────
    {
        "id": "d5", "type": "block", "position": pos(3, 0),
        "data": {
            "type": "tool",
            "label": "Wait: backend",
            "description": "Poll until delegator-backend deployment succeeds or fails",
            "integration": "railway",
            "config": {
                "action": "wait_for_deployment",
                "params": {
                    "deployment_id": "{{d3.deployment_id}}",
                    "timeout_seconds": 300,
                },
            },
        },
    },

    # ── Wait for frontend ─────────────────────────────────────────────────────
    {
        "id": "d6", "type": "block", "position": pos(3, 2),
        "data": {
            "type": "tool",
            "label": "Wait: frontend",
            "description": "Poll until delegator-ui deployment succeeds or fails",
            "integration": "railway",
            "config": {
                "action": "wait_for_deployment",
                "params": {
                    "deployment_id": "{{d4.deployment_id}}",
                    "timeout_seconds": 300,
                },
            },
        },
    },

    # ── Join: check both healthy ──────────────────────────────────────────────
    {
        "id": "d7", "type": "block", "position": pos(4, 1),
        "data": {
            "type": "logic",
            "label": "Both healthy?",
            "description": (
                "Check d5.healthy == true AND d6.healthy == true. "
                "Route 'pass' if both deployed successfully, 'fail' otherwise."
            ),
        },
    },

    # ── Notify: success ───────────────────────────────────────────────────────
    {
        "id": "d8", "type": "block", "position": pos(5, 0),
        "data": {
            "type": "output",
            "label": "Notify: deployed ✓",
            "description": (
                "✅ Delegator deployed successfully!\n"
                "Backend: {{d5.url}}\n"
                "Frontend: {{d6.url}}\n"
                "Triggered by: {{d1.__triggered_by}}"
            ),
            "integration": "slack",
            "config": {
                "integration": "slack",
                "channel": "#deployments",
            },
        },
    },

    # ── Notify: failure ───────────────────────────────────────────────────────
    {
        "id": "d9", "type": "block", "position": pos(5, 2),
        "data": {
            "type": "output",
            "label": "Notify: deploy failed ✗",
            "description": (
                "❌ Delegator deployment failed!\n"
                "Backend status: {{d5.status}} — {{d5.error}}\n"
                "Frontend status: {{d6.status}} — {{d6.error}}\n"
                "Check Railway dashboard for details."
            ),
            "integration": "slack",
            "config": {
                "integration": "slack",
                "channel": "#deployments",
            },
        },
    },
]

edges = [
    {"id": "e1-2",  "source": "d1", "target": "d2"},
    # After env lookup, fan out to both artifact deploys
    {"id": "e2-3",  "source": "d2", "target": "d3"},
    {"id": "e2-4",  "source": "d2", "target": "d4"},
    # Each artifact waits for its own deployment
    {"id": "e3-5",  "source": "d3", "target": "d5"},
    {"id": "e4-6",  "source": "d4", "target": "d6"},
    # Both wait blocks feed the join logic
    {"id": "e5-7",  "source": "d5", "target": "d7"},
    {"id": "e6-7",  "source": "d6", "target": "d7"},
    # Logic routes
    {"id": "e7-8",  "source": "d7", "target": "d8", "sourceHandle": "pass"},
    {"id": "e7-9",  "source": "d7", "target": "d9", "sourceHandle": "fail"},
]

graph = {"nodes": nodes, "edges": edges}

with engine.connect() as conn:
    result = conn.execute(text("SELECT id FROM workflows WHERE name = 'Deploy Delegator' LIMIT 1"))
    if result.fetchone():
        print("Already seeded — skipping.")
    else:
        conn.execute(text("""
            INSERT INTO workflows (id, workspace_id, name, default_mode)
            VALUES (:wf_id, :ws_id, 'Deploy Delegator', 'dag')
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
        print(f"Seeded 'Deploy Delegator' — {len(nodes)} blocks, {len(edges)} edges.")
        print(f"Workflow ID: {WORKFLOW_ID}")
        print()
        print("Artifacts configured:")
        print(f"  delegator-backend  service_id = {RAILWAY_BACKEND_SVC_ID}")
        print(f"  delegator-ui       service_id = {RAILWAY_FRONTEND_SVC_ID}")
        print(f"  project_id                    = {RAILWAY_PROJECT_ID}")
        print()
        print("To trigger a deployment, POST to:")
        print("  /webhooks/railway  (or run the workflow manually from the UI)")
