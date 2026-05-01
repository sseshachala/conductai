"""
Webhook endpoints for external services.

POST /webhooks/slack/interactions — receives interactive component payloads
  (Approve / Reject button clicks from approval block Slack messages).
"""
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import unquote_plus

import redis
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.run import Run, RunEvent

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

QUEUE_KEY = "marshal:runs:queue"


def _redis():
    return redis.from_url(settings.redis_url, decode_responses=True)


def _verify_slack_signature(request_body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack's request signing (v0 scheme)."""
    if not settings.slack_signing_secret:
        return True  # Skip verification in dev if secret not configured
    if abs(time.time() - int(timestamp)) > 300:
        return False  # Replay attack guard: reject if older than 5 minutes
    base = f"v0:{timestamp}:{request_body.decode()}"
    expected = "v0=" + hmac.new(
        settings.slack_signing_secret.encode(),
        base.encode(),
        hashlib.sha256,
    ).hexdigest()  # type: ignore[attr-defined]
    return hmac.compare_digest(expected, signature)


@router.post("/slack/interactions")
async def slack_interactions(request: Request, db: Session = Depends(get_db)):
    """
    Handle Slack interactive component payloads.
    Slack sends a URL-encoded body with a 'payload' field containing JSON.
    """
    body = await request.body()

    # Verify signature if signing secret is configured
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
    signature = request.headers.get("X-Slack-Signature", "")
    if not _verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Slack sends application/x-www-form-urlencoded with a 'payload' key
    body_str = body.decode()
    if body_str.startswith("payload="):
        payload_str = unquote_plus(body_str[len("payload="):])
    else:
        payload_str = body_str

    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid payload JSON")

    # Extract action
    actions = payload.get("actions", [])
    if not actions:
        return {"ok": True}

    action = actions[0]
    action_id = action.get("action_id", "")
    value = action.get("value", "")

    if action_id not in ("approve_run", "reject_run"):
        return {"ok": True}

    # Value format: "approve:{run_id}" or "reject:{run_id}"
    parts = value.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid action value format")

    decision_word, run_id_str = parts
    decision = "approved" if decision_word == "approve" else "rejected"

    run = db.query(Run).filter(Run.id == run_id_str).first()
    if not run:
        log.warning("Slack interaction for unknown run %s", run_id_str)
        return {"ok": True}

    if run.status != "paused":
        log.info("Run %s already %s — ignoring duplicate approval", run_id_str, run.status)
        return {"ok": True}

    block_id = run.current_block_id or ""
    approver = payload.get("user", {}).get("name", "slack-user")

    state = dict(run.state or {})
    state[f"__approval_{block_id}"] = decision
    state[f"__approver_{block_id}"] = approver
    run.state = state
    run.status = "pending"
    run.paused_at = None
    db.commit()

    event = RunEvent(
        run_id=run_id_str,
        block_id=block_id,
        kind="approval_received",
        payload={"decision": decision, "approver": approver, "source": "slack"},
    )
    db.add(event)
    db.commit()

    _redis().rpush(QUEUE_KEY, run_id_str)
    log.info("Run %s approval: %s by %s — re-queued", run_id_str, decision, approver)

    return {"ok": True}
