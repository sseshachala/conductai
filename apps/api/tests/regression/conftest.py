"""Regression harness shared fixtures.

Piggybacks on the parent tests/conftest.py for env setup. Adds:
- `client` — TestClient bound to the real app
- `requires_db` marker — skips gracefully when Postgres is not reachable
- `seeded_workspace` — creates a fresh workspace + agent token, yields, cleans up
- `load_fixture(name)` — helper to load a fixture JSON by name
"""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"
API_TOKEN_PREFIX = "cond_api_"


@pytest.fixture(scope="session")
def client() -> TestClient:
    from app.main import app  # noqa: WPS433
    return TestClient(app)


def _db_available() -> bool:
    try:
        from app.core.database import SessionLocal
        from app.models.workspace import Workspace
        with SessionLocal() as db:
            db.query(Workspace).limit(1).all()
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable")


def _mint_agent_token(db, workspace_id: uuid.UUID) -> str:
    from app.core.crypto import encrypt as _encrypt
    from app.modules.agent_identity.models import AgentIdentity

    plaintext = API_TOKEN_PREFIX + secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    tag = workspace_id.hex[:8]
    db.add(AgentIdentity(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name="regression-test-" + tag,
        provider="conduct",
        token_prefix=plaintext[:13],
        token_encrypted=_encrypt({"token": plaintext}),
        token_type="api",
        token_name="regression-harness",
        created_by_clerk_user_id="user_test_regression_" + tag,
        created_at=now,
        last_used_at=now,
        expires_at=None,
    ))
    db.commit()
    return plaintext


@pytest.fixture
def seeded_workspace():
    """Fresh workspace + agent token for one test. Cleaned up on teardown."""
    from app.core.database import SessionLocal
    from app.models.workspace import Workspace
    from app.modules.agent_identity.models import AgentIdentity

    ws_id = uuid.uuid4()
    tag = ws_id.hex[:8]
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        db.add(Workspace(
            id=ws_id,
            name="regression-" + tag,
            owner_id="user_test_regression_" + tag,
            plan="free",
            is_approved=True,
            created_at=now,
            updated_at=now,
        ))
        db.commit()
        token = _mint_agent_token(db, ws_id)

    yield ws_id, token

    with SessionLocal() as db:
        db.query(AgentIdentity).filter(AgentIdentity.workspace_id == ws_id).delete()
        ws = db.get(Workspace, ws_id)
        if ws is not None:
            db.delete(ws)
        db.commit()


def load_fixture(name: str) -> dict:
    """Load a fixture JSON file by name (without extension)."""
    path = FIXTURES_DIR / f"{name}.json"
    return json.loads(path.read_text())


def render_headers(headers: dict, token: str | None = None) -> dict:
    """Substitute {token} placeholder in header values."""
    if token is None:
        return dict(headers)
    return {k: v.replace("{token}", token) for k, v in headers.items()}
