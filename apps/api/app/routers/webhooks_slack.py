"""Slack interactivity webhook (split from webhooks.py).

Owns the shared ``/webhooks`` APIRouter. Route registration order is part of
the public contract, so the endpoint modules form an import chain:
webhooks_slack -> webhooks_inbound -> webhooks. Each module imports
``router`` from its predecessor.
"""
import json
import structlog
from urllib.parse import unquote_plus
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.models.run import Run, RunEvent
from app.routers.webhooks_common import (
    _enqueue_run,
    _get_run_workspace_id,
    _get_slack_signing_secret,
    _verify_slack_signature,
)

log = structlog.get_logger("app.routers.webhooks")


router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _handle_guard_slack_decision(
    *,
    db: Session,
    body: bytes,
    timestamp: str,
    signature: str,
    payload: dict,
    request_id_str: str,
    decision: str,
    platform_sig_ok: bool = False,
) -> dict:
    """Slack Approve/Reject on a GuardApprovalRequest. Mirrors the runtime
    path: re-verify signature against workspace secret, apply the decision,
    resume any workflow run tied to the approval, and stamp the Slack card.
    Silently no-ops on unknown/decided rows so retries stay idempotent.

    Wrapped in a broad try/except so Slack always gets 200 — the alternative
    is Slack rendering a red warning triangle on the message and the operator
    having no idea why. Real errors land in the log with a traceback so we
    can diagnose without another button click."""
    import uuid as _uuid
    from app.core.credentials import get_credential
    from app.modules.guard.approval import apply_decision, sweep_if_timed_out
    from app.modules.guard.models import GuardApprovalRequest
    from app.modules.guard.routers.approvals import _resume_workflow_run
    from app.runtime.integrations.slack import update_approval_message

    try:
        try:
            req_uuid = _uuid.UUID(str(request_id_str))
        except (ValueError, TypeError):
            log.warning("slack.guard_bad_request_id", request_id=request_id_str)
            return {"ok": True}

        # ponytail: same row lock as the HTTP decide path (#1197) — two Slack
        # clicks landing in the same ms serialize on commit; the loser reads
        # the fresh non-pending status and falls into the duplicate branch.
        row = (
            db.query(GuardApprovalRequest)
            .filter(GuardApprovalRequest.id == req_uuid)
            .with_for_update()
            .first()
        )
        if not row:
            log.warning("slack.unknown_guard_request", request_id=str(req_uuid))
            return {"ok": True}

        try:
            ws_creds = get_credential(db, str(row.workspace_id), "slack")
        except Exception:
            ws_creds = None
        ws_secret = (ws_creds or {}).get("signing_secret") or ""

        # Verify against workspace secret when the platform-level check was
        # skipped or when the workspace has its own (stricter) secret. If no
        # secret is available anywhere and the platform check didn't already
        # pass, we can't trust the request — drop it silently.
        needs_workspace_verify = (not platform_sig_ok) or (
            ws_secret and ws_secret != settings.slack_signing_secret
        )
        if needs_workspace_verify:
            if not ws_secret:
                log.warning("slack.guard_no_secret_to_verify", request_id=str(req_uuid))
                return {"ok": True}
            if not _verify_slack_signature(body, timestamp, signature, ws_secret):
                log.warning("slack.guard_bad_signature", request_id=str(req_uuid))
                return {"ok": True}

        approver = payload.get("user", {}).get("name", "slack-user")
        row = sweep_if_timed_out(db, row)
        if row.status == "pending":
            row = apply_decision(
                db, row,
                decision=decision,
                decider_email=None,
                decider_user_id=None,
                reason=f"slack:{approver}",
            )
            _resume_workflow_run(db, row, decision=decision, decider_email=None)
            log.info("guard.approval.slack_decision", request_id=str(row.id), decision=decision, approver=approver)
        else:
            log.info("guard.approval.slack_duplicate", request_id=str(row.id), status=row.status)

        msg_container = payload.get("container", {})
        msg_channel = msg_container.get("channel_id") or payload.get("channel", {}).get("id")
        msg_ts = msg_container.get("message_ts") or payload.get("message", {}).get("ts")
        if not (msg_channel and msg_ts):
            # Slack normally includes container.{channel_id,message_ts} on
            # every button click; this only fires on a malformed payload.
            log.warning(
                "slack.guard_update_skipped_no_channel_or_ts",
                request_id=str(row.id),
                has_channel=bool(msg_channel),
                has_ts=bool(msg_ts),
            )
        else:
            try:
                # Regression fix: the initial approval post uses
                # slack_token_for_channel() so a per-channel integration
                # can carry its own bot token (see approval.py ->
                # _fanout_slack). This update path used to only look at
                # the workspace-default `slack` credential — if the
                # approval was posted via a per-channel token the update
                # silently no-oped (empty token) and buttons stayed on
                # the message. Mirror the initial lookup by resolving
                # the notification-channel row for msg_channel first.
                default_token = (ws_creds or {}).get("token") or (ws_creds or {}).get("bot_token", "")
                token = default_token
                try:
                    from app.modules.guard.models import GuardNotificationChannel as _GNC
                    from app.modules.guard.routers.notifications import slack_token_for_channel as _tok_for
                    _ch_row = (
                        db.query(_GNC)
                        .filter(
                            _GNC.workspace_id == row.workspace_id,
                            _GNC.channel_type == "slack",
                            _GNC.channel_ref == msg_channel,
                        )
                        .first()
                    )
                    if _ch_row is not None:
                        token = _tok_for(db, row.workspace_id, _ch_row.integration_id, default_token) or default_token
                except Exception as _exc:  # noqa: BLE001 — cred lookup must never block the ack
                    log.warning("slack.guard_update_token_lookup_failed", request_id=str(row.id), err=str(_exc))
                if not token:
                    log.warning(
                        "slack.guard_update_skipped_no_token",
                        request_id=str(row.id),
                        channel=msg_channel,
                    )
                else:
                    update_approval_message(token, msg_channel, msg_ts, row.status, approver, rule_id=row.rule_id)
            except Exception as e:
                log.warning("slack.guard_update_message_failed", request_id=str(row.id), error=str(e))
    except Exception as _exc:
        import traceback as _tb
        log.error(
            "slack.guard_decision_unhandled",
            request_id=request_id_str,
            decision=decision,
            err_type=type(_exc).__name__,
            err=str(_exc),
            tb=_tb.format_exc(),
        )
    return {"ok": True}


@router.post("/slack/interactions")
async def slack_interactions(request: Request, bg: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Handle Slack interactive component payloads.
    Slack sends a URL-encoded body with a 'payload' field containing JSON.
    """
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
    signature = request.headers.get("X-Slack-Signature", "")

    # Signature verification: platform-level secret is optional. When set, use
    # it as a zero-DB gate that rejects unsigned traffic before any lookup.
    # When unset, the guard/run branches below verify against the workspace's
    # own signing_secret credential (one indexed DB read on unsigned requests
    # instead of an immediate 401 — small trade-off customers accept in
    # exchange for not having to manage a platform env var).
    platform_secret = settings.slack_signing_secret or ""
    platform_sig_ok = bool(platform_secret) and _verify_slack_signature(
        body, timestamp, signature, platform_secret,
    )
    if platform_secret and not platform_sig_ok:
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Parse payload
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

    if action_id not in ("approve_run", "reject_run", "guard_approve", "guard_reject"):
        return {"ok": True}

    # Value format: "approve:{id}" or "reject:{id}"
    parts = value.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid action value format")

    decision_word, target_id_str = parts
    decision = "approved" if decision_word == "approve" else "rejected"

    if action_id in ("guard_approve", "guard_reject"):
        # Slack enforces a 3s response deadline on interactive components. The
        # decision handler does DB writes + a Slack API round-trip to update
        # the message, which can exceed 3s and cause Slack to retry (visible
        # to the user as "had to click twice"). Push the work to a background
        # task and return 200 immediately.
        def _bg_guard_decision():
            from app.core.database import SessionLocal
            _db = SessionLocal()
            try:
                _handle_guard_slack_decision(
                    db=_db,
                    body=body,
                    timestamp=timestamp,
                    signature=signature,
                    payload=payload,
                    request_id_str=target_id_str,
                    decision=decision,
                    platform_sig_ok=platform_sig_ok,
                )
            finally:
                _db.close()
        bg.add_task(_bg_guard_decision)
        return {"ok": True}

    run_id_str = target_id_str

    run = db.query(Run).filter(Run.id == run_id_str).first()
    if not run:
        log.warning("slack.unknown_run", run_id=run_id_str)
        return {"ok": True}

    # Workspace signing-secret verify. Required when the platform-level check
    # was skipped (no platform secret configured) OR when the workspace has
    # its own stricter secret. If we can't verify anywhere, drop the request.
    signing_secret = _get_slack_signing_secret(run, db)
    needs_workspace_verify = (not platform_sig_ok) or (
        signing_secret and signing_secret != settings.slack_signing_secret
    )
    if needs_workspace_verify:
        if not signing_secret:
            log.warning("slack.run_no_secret_to_verify", run_id=run_id_str)
            return {"ok": True}
        if not _verify_slack_signature(body, timestamp, signature, signing_secret):
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

    block_id = run.current_block_id or ""
    approver = payload.get("user", {}).get("name", "slack-user")

    if run.status == "paused":
        # Atomic CAS: only the first concurrent Slack click wins.
        # Merge the decision into state and flip status to 'pending' in one statement.
        from sqlalchemy import text as _text
        state = dict(run.state or {})
        state[f"__approval_{block_id}"] = decision
        state[f"__approver_{block_id}"] = approver
        cas_result = db.execute(
            _text(
                "UPDATE runs SET status='pending', paused_at=NULL, state=CAST(:state AS jsonb) "
                "WHERE id=:id AND status='paused' "
                "RETURNING id"
            ),
            {"state": json.dumps(state), "id": run_id_str},
        ).fetchone()

        if cas_result:
            # Write the event and enqueue only if we won the CAS.
            db.add(RunEvent(
                run_id=run_id_str,
                block_id=block_id,
                kind="approval_received",
                payload={"decision": decision, "approver": approver, "source": "slack"},
            ))
            db.commit()
            try:
                _enqueue_run(run_id_str)
            except Exception:
                log.error("slack.redis_enqueue_failed", run_id=run_id_str)
            log.info("run.approval_gate", run_id=run_id_str, decision=decision, approver=approver)
        else:
            # Duplicate click — run already resumed, just ack to Slack.
            db.commit()
            log.info("run.duplicate_approval_ignored", run_id=run_id_str, decision=decision)
    else:
        # Post-run feedback — record verdict, do not re-queue.
        db.add(RunEvent(
            run_id=run_id_str,
            block_id=block_id,
            kind="approval_received",
            payload={"decision": decision, "approver": approver, "source": "slack"},
        ))
        db.commit()
        log.info("run.post_run_verdict", run_id=run_id_str, decision=decision, approver=approver)

    # Update the Slack message to replace buttons with the decision stamp
    msg_container = payload.get("container", {})
    msg_channel = msg_container.get("channel_id") or payload.get("channel", {}).get("id")
    msg_ts = msg_container.get("message_ts") or payload.get("message", {}).get("ts")
    if msg_channel and msg_ts:
        try:
            from app.runtime.integrations.slack import update_approval_message
            from app.core.credentials import get_credential
            workspace_id = _get_run_workspace_id(run, db)
            if workspace_id:
                slack_creds = get_credential(db, workspace_id, "slack")
                if slack_creds:
                    slack_token = slack_creds.get("token") or slack_creds.get("bot_token", "")
                    update_approval_message(slack_token, msg_channel, msg_ts, decision, approver)
        except Exception as e:
            log.warning("slack.update_message_failed", error=str(e))

    return {"ok": True}
