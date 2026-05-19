"""
Seed a stable test workspace + test user + dummy credentials so smoke tests
can exercise the full API surface without needing real GitHub / Slack / DO
accounts.

Run inside the API container (or against a local DB):

    docker compose exec api python seed_test_user.py
    # or, locally:
    DATABASE_URL=postgresql://marshal:marshal@localhost:5432/marshal \
      python seed_test_user.py

Idempotent — safe to re-run.

What it creates:

  workspace_id = 11111111-1111-1111-1111-111111111111   (the "test" workspace)
  user_id      = "test-user"                            (in JWT claims this would be the `sub`)

  Workflows:
    - "Smoke — empty"   : minimal valid YAML, no external calls
    - "Smoke — ai-ready": the ai_ready playbook with dummy credential refs

  Dummy credentials in the test workspace:
    - github         : token=dummy_gh_token
    - slack          : token=dummy_slack_token
    - digitalocean   : token=dummy_do_token,
                       ssh_key_fingerprint=00:00:...,
                       ssh_private_key=<rsa fake>
    - email          : resend_api_key=dummy_resend_key

The dummy credentials are intentionally non-functional. Real runs against
these workflows will fail at the first network call — which is what we want
for Tier-1/Tier-2 smoke tests. Dry-run mode short-circuits before any real
API call, so the dry-run path returns success.
"""
from __future__ import annotations

import json
import sys
import uuid

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.core.crypto import encrypt
from app.dsl import load_workflow_yaml, yaml_to_graph

TEST_WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
TEST_USER_ID = "test-user"
TEST_WORKSPACE_NAME = "Smoke-test workspace"

# -- Workflows --------------------------------------------------------------

SMOKE_EMPTY_YAML = """\
name: Smoke — empty
version: 1
description: Trivial valid workflow used by smoke tests.

on:
  manual:
    next: greet

blocks:
  greet:
    type: output
    output:
      via: slack
      slack:
        channel: "#smoke"
"""

# We bind the ai-ready playbook to test workspace creds. The actual remote
# execution will fail at SSH (dummy private key), but parse, persist, and
# dry-run will all succeed.
SMOKE_AI_READY_YAML = """\
name: Smoke — ai-ready
version: 1
description: ai-ready playbook with dummy credentials for smoke testing.

on:
  manual:
    next: notify

blocks:
  notify:
    type: output
    output:
      via: slack
      slack:
        channel: "#smoke"
"""

WORKFLOWS = [
    ("22222222-2222-2222-2222-222222222222", SMOKE_EMPTY_YAML),
    ("33333333-3333-3333-3333-333333333333", SMOKE_AI_READY_YAML),
]

# -- Dummy credentials ------------------------------------------------------

DUMMY_CREDENTIALS = {
    "github": {"token": "dummy_gh_token"},
    "slack": {"token": "dummy_slack_token", "bot_token": "dummy_slack_token"},
    "digitalocean": {
        "token": "dummy_do_token",
        "ssh_key_fingerprint": "00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00",
        # Fake but well-formed OpenSSH-style header so paramiko surfaces a key
        # parse error, not a "missing field" error, during smoke runs.
        "ssh_private_key": (
            "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            "ZmFrZS1kdW1teS1zc2gta2V5LWZvci10ZXN0aW5n\n"
            "-----END OPENSSH PRIVATE KEY-----\n"
        ),
    },
    "email": {"resend_api_key": "dummy_resend_key"},
}


def _upsert_workspace(conn) -> None:
    conn.execute(
        text(
            """
            INSERT INTO workspaces (id, name, owner_id, is_approved, plan)
            VALUES (:id, :name, :owner, true, 'free')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, is_approved = true
            """
        ),
        {"id": TEST_WORKSPACE_ID, "name": TEST_WORKSPACE_NAME, "owner": TEST_USER_ID},
    )


def _upsert_user(conn) -> None:
    # Users table may have varying columns; insert what we know exists.
    cols = [r[0] for r in conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='users'"
    )).fetchall()]
    if "id" not in cols:
        return
    if "external_id" in cols:
        conn.execute(
            text(
                """
                INSERT INTO users (id, external_id, workspace_id)
                VALUES (:id, :ext, :ws)
                ON CONFLICT DO NOTHING
                """
            ),
            {"id": str(uuid.uuid4()), "ext": TEST_USER_ID, "ws": TEST_WORKSPACE_ID},
        )


def _upsert_credentials(conn) -> None:
    # `handle` is what blocks reference; `service` is the integration kind.
    # For the seeded test workspace we just make them the same string —
    # workflows use the handle, the runtime resolves credentials by handle.
    for handle, payload in DUMMY_CREDENTIALS.items():
        blob = encrypt(payload)
        conn.execute(
            text(
                """
                INSERT INTO integrations
                    (id, workspace_id, service, auth_method, handle, encrypted_credentials)
                VALUES
                    (:id, :ws, :service, :auth_method, :handle, :blob)
                ON CONFLICT (workspace_id, handle) DO UPDATE
                  SET encrypted_credentials = EXCLUDED.encrypted_credentials,
                      service = EXCLUDED.service,
                      auth_method = EXCLUDED.auth_method
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "ws": TEST_WORKSPACE_ID,
                "service": handle,
                "auth_method": "api_key",  # dummy creds are api-key shaped
                "handle": handle,
                "blob": blob,
            },
        )


def _upsert_workflow(conn, workflow_id: str, yaml_text: str) -> None:
    dsl = load_workflow_yaml(yaml_text)
    graph = yaml_to_graph(dsl)

    existing = conn.execute(
        text("SELECT id FROM workflows WHERE id = :id"),
        {"id": workflow_id},
    ).fetchone()

    if not existing:
        conn.execute(
            text(
                """
                INSERT INTO workflows (id, workspace_id, name, default_mode)
                VALUES (:id, :ws, :name, 'dag')
                """
            ),
            {"id": workflow_id, "ws": TEST_WORKSPACE_ID, "name": dsl.name},
        )

    version_id = conn.execute(
        text(
            """
            INSERT INTO workflow_versions (workflow_id, yaml_source, graph)
            VALUES (:wf_id, :yaml, cast(:graph as jsonb))
            RETURNING id
            """
        ),
        {"wf_id": workflow_id, "yaml": yaml_text, "graph": json.dumps(graph)},
    ).fetchone()[0]

    conn.execute(
        text("UPDATE workflows SET name = :name, current_version_id = :vid WHERE id = :id"),
        {"name": dsl.name, "vid": str(version_id), "id": workflow_id},
    )


def main() -> int:
    engine = create_engine(settings.sqlalchemy_database_url)
    with engine.begin() as conn:
        _upsert_workspace(conn)
        _upsert_user(conn)
        _upsert_credentials(conn)
        for wf_id, yaml_text in WORKFLOWS:
            _upsert_workflow(conn, wf_id, yaml_text)

    print(f"Seeded test workspace: {TEST_WORKSPACE_ID}")
    print(f"Seeded test workflows:")
    for wf_id, _ in WORKFLOWS:
        print(f"  - {wf_id}")
    print(f"Dummy credentials installed: {', '.join(DUMMY_CREDENTIALS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
