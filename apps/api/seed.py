"""
Seed the dev DB with the Story → PR reference workflow.
Run with: python seed.py
"""
import json
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.database_url)

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

# Block positions — 4 columns, rows spaced 160px apart
def pos(col, row):
    return {"x": 60 + col * 200, "y": 60 + row * 160}

nodes = [
    {"id": "b1",  "type": "block", "position": pos(0, 0), "data": {"type": "trigger",  "label": "Story ready",        "description": "Linear webhook when label = ai-ready", "integration": "linear"}},
    {"id": "b2",  "type": "block", "position": pos(1, 0), "data": {"type": "tool",     "label": "Fetch story",         "description": "Pull title, description, criteria",    "integration": "linear"}},
    {"id": "b3",  "type": "block", "position": pos(2, 0), "data": {"type": "output",   "label": "Slack: starting",     "description": "Post 'working on STORY-X'",            "integration": "slack"}},
    {"id": "b4",  "type": "block", "position": pos(3, 0), "data": {"type": "tool",     "label": "Provision sandbox",   "description": "Spin up Ubuntu droplet",               "integration": "digitalocean"}},
    {"id": "b5",  "type": "block", "position": pos(0, 1), "data": {"type": "tool",     "label": "Checkout",            "description": "Clone repo, create feat/STORY-X branch","integration": "github"}},
    {"id": "b6",  "type": "block", "position": pos(1, 1), "data": {"type": "brain",    "label": "Generate code",       "description": "Implement story with file/shell tools", "isAgentic": True}},
    {"id": "b7",  "type": "block", "position": pos(2, 1), "data": {"type": "tool",     "label": "Run tests",           "description": "Execute unit + smoke suites"}},
    {"id": "b8",  "type": "block", "position": pos(3, 1), "data": {"type": "logic",    "label": "Pass or fail?",       "description": "Branch on test exit code"}},
    {"id": "b9",  "type": "block", "position": pos(0, 2), "data": {"type": "brain",    "label": "Fix loop",            "description": "Read failures, patch — max 3 tries",   "isAgentic": True}},
    {"id": "b10", "type": "block", "position": pos(1, 2), "data": {"type": "tool",     "label": "Push + draft PR",     "description": "Push branch, open draft PR",           "integration": "github"}},
    {"id": "b11", "type": "block", "position": pos(2, 2), "data": {"type": "tool",     "label": "Wait for preview",    "description": "Poll until Vercel deploy is READY",    "integration": "vercel"}},
    {"id": "b12", "type": "block", "position": pos(3, 2), "data": {"type": "approval", "label": "Await reviewer",      "description": "DM with PR + preview link, pause until ✓", "integration": "slack"}},
    {"id": "b13", "type": "block", "position": pos(1, 3), "data": {"type": "tool",     "label": "Merge to main",       "description": "Squash-merge on approval",             "integration": "github"}},
    {"id": "b14", "type": "block", "position": pos(2, 3), "data": {"type": "tool",     "label": "Wait for prod",       "description": "Poll until production deploy is READY","integration": "vercel"}},
    {"id": "b15", "type": "block", "position": pos(3, 3), "data": {"type": "output",   "label": "Notify shipped",      "description": "Post confirmation with prod URL",       "integration": "slack"}},
    {"id": "b16", "type": "block", "position": pos(0, 3), "data": {"type": "cleanup",  "label": "Tear down",           "description": "Destroy droplet — always runs",        "integration": "digitalocean"}},
]

edges = [
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

graph = {"nodes": nodes, "edges": edges}

with engine.connect() as conn:
    # Check if already seeded
    result = conn.execute(text("SELECT id FROM workflows WHERE name = 'Story → PR agent' LIMIT 1"))
    if result.fetchone():
        print("Already seeded — skipping.")
    else:
        # Insert workflow first (no current_version_id yet)
        conn.execute(text("""
            INSERT INTO workflows (id, workspace_id, name, default_mode)
            VALUES ('00000000-0000-0000-0000-000000000002', :workspace_id, 'Story → PR agent', 'dag')
        """), {"workspace_id": WORKSPACE_ID})

        # Insert version with workflow_id
        version_id = conn.execute(text("""
            INSERT INTO workflow_versions (workflow_id, graph)
            VALUES ('00000000-0000-0000-0000-000000000002', cast(:graph as jsonb))
            RETURNING id
        """), {"graph": json.dumps(graph)}).fetchone()[0]

        # Point workflow at version
        conn.execute(text("""
            UPDATE workflows SET current_version_id = :version_id
            WHERE id = '00000000-0000-0000-0000-000000000002'
        """), {"version_id": str(version_id)})

        conn.commit()
        print(f"Seeded 'Story → PR agent' with {len(nodes)} blocks and {len(edges)} edges.")
