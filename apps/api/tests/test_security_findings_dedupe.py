"""Verify ingest_finding is idempotent on (workspace, repo, type, file, description).

Rerunning a scanner or threat-modeler must not spawn N duplicate findings
+ N duplicate security_loop cascades. See conductai#998 + #1000.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.security_finding import SecurityFinding
from app.routers.security import ingest_finding


class _Body:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _body(**overrides):
    defaults = dict(
        tool="threat_modeler",
        severity="high",
        type="secret-leak",
        file="coworker/secrets.py",
        line=42,
        description="Hardcoded HMAC fallback secret allows signature forgery",
        suggested_fix="Rotate and require config",
        repo_full_name="sseshachala/openworker",
        commit_sha=None,
        source_run_id=None,
        reporter_email=None,
    )
    defaults.update(overrides)
    return _Body(**defaults)


def _mock_db_with(existing_row):
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value = q
    q.order_by.return_value = q
    q.first.return_value = existing_row
    return db


def test_dedupe_returns_existing_for_matching_open_finding():
    """Same (workspace, repo, type, file, description[:200]) → return existing."""
    existing = SecurityFinding(
        id="00000000-0000-0000-0000-000000000001",
        workspace_id="ws-1",
        tool="prev_scanner",
        severity="high",
        type="secret-leak",
        file="coworker/secrets.py",
        description="Hardcoded HMAC fallback secret allows signature forgery",
        repo_full_name="sseshachala/openworker",
        status="open",
    )
    db = _mock_db_with(existing)
    resp = MagicMock(status_code=201)

    with patch("app.routers.security._trigger_security_loop") as mock_loop:
        got = ingest_finding(resp, _body(), db=db, workspace_id="ws-1")

    assert got is existing
    assert resp.status_code == 200, "dedupe hit must return 200 not 201"
    db.add.assert_not_called()  # no new row inserted
    mock_loop.assert_not_called()  # no duplicate security_loop cascade


def test_creates_new_when_no_active_duplicate():
    """No matching active finding → creates a new one (201)."""
    db = _mock_db_with(None)
    resp = MagicMock(status_code=201)

    with patch("app.routers.security._trigger_security_loop"):
        got = ingest_finding(resp, _body(), db=db, workspace_id="ws-1")

    assert got is not None
    db.add.assert_called_once()
    # status remains 201 (default) when we insert
    assert resp.status_code == 201


def test_different_description_creates_new():
    """Description mismatch → treat as new finding."""
    existing = SecurityFinding(
        id="00000000-0000-0000-0000-000000000002",
        workspace_id="ws-1",
        type="secret-leak",
        file="coworker/secrets.py",
        description="A completely different finding text",
        repo_full_name="sseshachala/openworker",
        status="open",
    )
    # In reality, .filter(description[:200] == body_desc[:200]) would return None
    # since descriptions differ. Simulate that:
    db = _mock_db_with(None)
    resp = MagicMock(status_code=201)

    with patch("app.routers.security._trigger_security_loop"):
        ingest_finding(resp, _body(), db=db, workspace_id="ws-1")

    db.add.assert_called_once()
