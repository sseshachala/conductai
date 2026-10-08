"""Shared webhook helpers: run-queue enqueue + Slack signature / signing-secret lookup
(split from webhooks.py).
"""
import hashlib
import hmac
import time
import redis
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.run import Run


QUEUE_KEY = "marshal:runs:queue"
QUEUE_MAX_DEPTH = 50_000


def _redis():
    return redis.from_url(settings.redis_url, decode_responses=True)


def _enqueue_run(run_id: str) -> None:
    r = _redis()
    depth = r.llen(QUEUE_KEY)
    if depth >= QUEUE_MAX_DEPTH:
        raise HTTPException(
            status_code=503,
            detail=f"Run queue is at capacity ({depth} pending). Try again shortly.",
        )
    r.rpush(QUEUE_KEY, run_id)


def _verify_slack_signature(request_body: bytes, timestamp: str, signature: str, signing_secret: str) -> bool:
    """Verify Slack's request signing (v0 scheme)."""
    if not signing_secret:
        return False
    if abs(time.time() - int(timestamp)) > 300:
        return False  # Replay attack guard
    base = f"v0:{timestamp}:{request_body.decode()}"
    expected = "v0=" + hmac.new(
        signing_secret.encode(),
        base.encode(),
        hashlib.sha256,
    ).hexdigest()  # type: ignore[attr-defined]
    return hmac.compare_digest(expected, signature)


def _get_run_workspace_id(run: "Run", db: Session) -> str | None:
    """Resolve workspace_id for a run via its workflow_version → workflow chain."""
    from sqlalchemy import text as _text
    row = db.execute(
        _text("""
            SELECT w.workspace_id
            FROM runs r
            JOIN workflow_versions wv ON r.workflow_version_id = wv.id
            JOIN workflows w ON wv.workflow_id = w.id
            WHERE r.id = :run_id
            LIMIT 1
        """),
        {"run_id": str(run.id)},
    ).fetchone()
    return str(row[0]) if row else None


def _get_slack_signing_secret(run: "Run", db: Session) -> str:
    """Look up the Slack signing secret from the run's workspace credential."""
    from app.core.credentials import get_credential

    workspace_id = _get_run_workspace_id(run, db)
    if not workspace_id:
        return settings.slack_signing_secret or ""

    creds = get_credential(db, workspace_id, "slack")
    return creds.get("signing_secret") or settings.slack_signing_secret or ""
