"""
End-to-end tests for the GitHub webhook critical path.

Three scenarios:
  1. Issue-labeled event routes to the *correct* workflow when two share a repo
     but watch different labels.
  2. An unknown label fires nobody — 0 runs queued.
  3. The HTTP handler rejects a bad signature with 401 before any DB access.

All tests run without a real Postgres or Redis instance.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-webhook-secret-xyz")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

from fastapi.testclient import TestClient

# Import all models so SQLAlchemy mapper relationships resolve before any Run() instantiation
import app.models.environment  # noqa: F401
import app.models.integration  # noqa: F401
import app.models.project  # noqa: F401
import app.models.run  # noqa: F401
import app.models.workspace  # noqa: F401

from app.routers.webhooks import (
    _normalize_github_issue_labeled_payload,
    _trigger_github_workflows,
)

WEBHOOK_SECRET = "test-webhook-secret-xyz"
REPO = "my-org/my-repo"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_version(event_type: str, repo: str, labels: list[str] | None = None) -> SimpleNamespace:
    """Minimal WorkflowVersion with a trigger node."""
    config: dict = {"event_type": event_type, "repo_allowlist": repo}
    if labels is not None:
        config["labels"] = labels
    node = {"data": {"type": "trigger", "config": config}}
    version = SimpleNamespace(
        id=str(uuid.uuid4()),
        graph={"nodes": [node]},
    )
    return version


def _make_db(*versions: SimpleNamespace) -> MagicMock:
    """Mock Session whose query chain returns the provided versions."""
    db = MagicMock()
    # Support both filtered (with workspace_id) and unfiltered paths
    chain = db.query.return_value.join.return_value
    chain.all.return_value = list(versions)
    chain.filter.return_value.all.return_value = list(versions)
    # Run.flush / Run.commit are no-ops; track what was added
    added: list = []
    db.add.side_effect = lambda obj: added.append(obj)
    db._added = added  # type: ignore[attr-defined]
    return db


def _labeled_payload(label: str, repo: str = REPO) -> dict:
    owner, name = repo.split("/", 1)
    return {
        "action": "labeled",
        "label": {"name": label},
        "issue": {
            "number": 42,
            "id": 1,
            "title": "Test issue",
            "body": "body",
            "html_url": f"https://github.com/{repo}/issues/42",
            "user": {"login": "alice"},
            "labels": [{"name": label}],
        },
        "repository": {
            "id": 1,
            "full_name": repo,
            "name": name,
            "owner": {"login": owner},
            "default_branch": "main",
            "clone_url": f"https://github.com/{repo}.git",
        },
        "sender": {"login": "alice"},
    }


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()  # type: ignore[attr-defined]


# ── Test 1: label routing — only matching workflow fires ──────────────────────

def test_issue_labeled_routes_to_correct_workflow():
    """
    Two workflows on the same repo watch different labels.
    Posting 'autopilot-ready' should queue exactly one run for wf1,
    and zero runs for wf2 (which watches 'deploy-ready').
    """
    wf1 = _make_version("github_issue_labeled", REPO, labels=["autopilot-ready"])
    wf2 = _make_version("github_issue_labeled", REPO, labels=["deploy-ready"])
    db = _make_db(wf1, wf2)

    payload = _labeled_payload("autopilot-ready")
    normalized = _normalize_github_issue_labeled_payload(payload)
    initial_state = {"github_issue": normalized["issue"], "github_trigger": normalized}

    with patch("app.routers.webhooks._redis") as mock_redis_factory:
        redis_client = MagicMock()
        mock_redis_factory.return_value = redis_client

        queued = _trigger_github_workflows(
            db, "github_issue_labeled", normalized, initial_state, workspace_id=None
        )

    assert len(queued) == 1, f"Expected 1 run queued, got {len(queued)}"
    assert redis_client.rpush.call_count == 1

    # The Run that was added must be for wf1's version
    added_runs = [obj for obj in db._added if hasattr(obj, "workflow_version_id")]
    assert len(added_runs) == 1
    assert str(added_runs[0].workflow_version_id) == wf1.id


# ── Test 2: unknown label — no workflow fires ─────────────────────────────────

def test_issue_labeled_unknown_label_fires_nobody():
    """
    When the incoming label doesn't match any configured workflow,
    no runs should be queued.
    """
    wf1 = _make_version("github_issue_labeled", REPO, labels=["autopilot-ready"])
    db = _make_db(wf1)

    payload = _labeled_payload("random-unrelated-label")
    normalized = _normalize_github_issue_labeled_payload(payload)
    initial_state = {"github_issue": normalized["issue"], "github_trigger": normalized}

    with patch("app.routers.webhooks._redis") as mock_redis_factory:
        redis_client = MagicMock()
        mock_redis_factory.return_value = redis_client

        queued = _trigger_github_workflows(
            db, "github_issue_labeled", normalized, initial_state, workspace_id=None
        )

    assert queued == [], f"Expected no runs, got {queued}"
    redis_client.rpush.assert_not_called()


# ── Test 3: bad signature → 401 before any DB work ───────────────────────────

def test_github_webhook_rejects_bad_signature():
    """
    A POST with a wrong X-Hub-Signature-256 must return 401.
    The DB must never be touched — signature is verified first.
    """
    from app.main import app
    from app.core.database import get_db

    db_mock = MagicMock()

    def override_db():
        yield db_mock

    app.dependency_overrides[get_db] = override_db

    body = json.dumps(_labeled_payload("autopilot-ready")).encode()
    bad_sig = _sign(body, secret="wrong-secret")

    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": bad_sig,
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
    db_mock.query.assert_not_called()
