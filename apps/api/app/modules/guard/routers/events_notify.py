"""ConductGuard events — block notifications (Slack/PagerDuty/email/webhook fan-out) and spend-budget alerts."""

import structlog
from sqlalchemy.orm import Session
from app.modules.guard.models import GuardAuditEvent, GuardConfig, GuardSpendBudget
from app.modules.guard.routers.events_common import (
    _now,
)

log = structlog.get_logger("app.modules.guard.routers.events")


def notify_guard_block(
    db: Session, workspace_id, *,
    decision: str, rule_id: str | None,
    user_email: str | None, tool: str | None = None,
    provider: str | None = None, source: str = "hook",
) -> None:
    """Single entry point for Guard block/warn Slack notifications.

    Fans out via the #1142 per-action-tier notification channels table when any
    rows exist for this workspace + action; falls back to the legacy single-
    channel setup on guard_config otherwise. Once the operator adds a channel
    via /theguard/settings > Notifications, that new config takes over.
    """
    import uuid as _uuid
    from app.modules.guard.models import GuardConfig as _GC
    from app.models.workspace import Workspace as _WS
    from app.modules.guard.routers.notifications import resolve_channels as _resolve_channels
    ws = _uuid.UUID(str(workspace_id)) if not isinstance(workspace_id, _uuid.UUID) else workspace_id
    cfg = db.query(_GC).filter(_GC.workspace_id == ws).first()
    ws_name = db.query(_WS.name).filter(_WS.id == ws).scalar()
    ws_label = f"{ws_name} · `{str(ws)[:8]}`" if ws_name else f"`{str(ws)[:8]}`"

    icon = "🚨" if decision == "blocked" else "⚠️"
    lines = [f"{icon} *Guard {decision}* — `{rule_id or source}`"]
    lines.append(f"• Workspace: {ws_label}")
    if user_email:
        lines.append(f"• User: {user_email}")
    if tool:
        lines.append(f"• Tool: `{tool}`")
    if provider:
        lines.append(f"• Provider: `{provider}` · via {source}")
    text_msg = "\n".join(lines)

    # #1142 Phase 1+2A+2B+2C — fan out to per-action channels if configured.
    # Split by channel_type: each transport gets a shape it can consume.
    action = "block" if decision == "blocked" else "warn" if decision == "warned" else "audit"
    channels = _resolve_channels(db, ws, action)
    if channels:
        by_type: dict[str, list] = {"slack": [], "webhook": [], "pagerduty": [], "email": []}
        for c in channels:
            by_type.setdefault(c.channel_type, []).append(c)
        if by_type["slack"]:
            _fanout_slack(db, ws, by_type["slack"], text_msg)
        if by_type["webhook"]:
            _fanout_webhook(by_type["webhook"], {
                "event": "guard.decision",
                "action": action,
                "decision": decision,
                "rule_id": rule_id,
                "workspace_id": str(ws),
                "user_email": user_email,
                "tool": tool,
                "provider": provider,
                "source": source,
                "message": text_msg,
            })
        if by_type["pagerduty"]:
            _fanout_pagerduty(by_type["pagerduty"], action, rule_id, text_msg)
        if by_type["email"]:
            _fanout_email(
                db, ws, by_type["email"],
                subject=f"[Guard {decision}] {rule_id or source}",
                html=(
                    f"<p><strong>Guard {decision}</strong> — rule <code>{rule_id or source}</code></p>"
                    + f"<p>Workspace: {ws_name or ''} <code>{str(ws)[:8]}</code></p>"
                    + (f"<p>User: {user_email}</p>" if user_email else "")
                    + (f"<p>Tool: <code>{tool}</code></p>" if tool else "")
                    + (f"<p>Provider: <code>{provider}</code> via {source}</p>" if provider else "")
                ),
            )
        return

    # Legacy fallback — single alert_channel gated by notify_on_block.
    if not cfg or not cfg.notify_on_block:
        return
    _send_guard_slack(db, cfg, text_msg)


def _fanout_slack(db: Session, workspace_id, channels, text_msg: str, *, blocks: list | None = None) -> None:
    """Post text_msg to every Slack channel in `channels`. Silently skips any
    that lack credentials or fail — one bad channel must not block the others.

    Per-channel env: honors channel.integration_id via slack_token_for_channel;
    falls back to the workspace-default Slack cred when not set.

    Pass `blocks` for interactive messages (e.g. Guard approval Approve/Reject
    buttons); text_msg is kept as the fallback rendered by Slack clients that
    can't display blocks."""
    from app.core.credentials import get_credential
    from app.modules.guard.routers.notifications import slack_token_for_channel
    from app.runtime.integrations.slack import post_message

    try:
        default_creds = get_credential(db, str(workspace_id), "slack")
    except Exception:
        default_creds = None
    default_token = (default_creds or {}).get("token") or (default_creds or {}).get("bot_token") or ""

    for ch in channels:
        if ch.channel_type != "slack":
            continue
        token = slack_token_for_channel(db, workspace_id, ch.integration_id, default_token)
        if not token:
            continue
        try:
            post_message(token=token, channel=ch.channel_ref, text=text_msg, blocks=blocks)
        except Exception:
            pass  # per-channel failure must not stop the fan-out


def _pd_severity(action: str) -> str:
    return {"block": "error", "approval": "error", "warn": "warning", "audit": "info"}.get(action, "info")


def _fanout_pagerduty(channels, action: str, rule_id, message: str) -> None:
    """POST a PagerDuty Events API v2 trigger for each channel.
    channel_ref is the routing key (integration key from a PD service)."""
    if not channels:
        return
    try:
        import httpx
    except ImportError:
        return
    body_template = {
        "event_action": "trigger",
        "payload": {
            "summary": f"Guard {action}: {rule_id or 'policy event'}",
            "severity": _pd_severity(action),
            "source": "conduct-guard",
            "custom_details": {"message": message},
        },
    }
    for ch in channels:
        if ch.channel_type != "pagerduty":
            continue
        try:
            payload = dict(body_template)
            payload["routing_key"] = ch.channel_ref
            payload["dedup_key"] = f"conduct-guard-{ch.id}-{rule_id or 'noid'}"
            httpx.post("https://events.pagerduty.com/v2/enqueue", json=payload, timeout=10.0)
        except Exception:
            pass


def _fanout_email(db, workspace_id, channels, subject: str, html: str) -> None:
    """Send an email to each recipient. Uses app.core.email.send_email which
    handles workspace-scoped Resend/SendGrid credentials + platform fallback."""
    if not channels:
        return
    try:
        from app.core.email import send_email
    except ImportError:
        return
    for ch in channels:
        if ch.channel_type != "email":
            continue
        try:
            send_email(
                to=ch.channel_ref,
                subject=subject,
                html=html,
                workspace_id=str(workspace_id),
                db=db,
            )
        except Exception:
            pass


def _fanout_webhook(channels, payload: dict) -> None:
    """POST a JSON payload to every webhook channel. Same fail-soft contract
    as _fanout_slack — one bad URL does not block the others."""
    if not channels:
        return
    try:
        import httpx
    except ImportError:
        return
    for ch in channels:
        if ch.channel_type != "webhook":
            continue
        try:
            httpx.post(ch.channel_ref, json=payload, timeout=10.0)
        except Exception:
            pass  # per-channel failure must not stop the fan-out


def _send_guard_slack(db: Session, config: GuardConfig, text_msg: str) -> None:
    """Fire-and-forget Slack notification. Silently skips if not configured."""
    from app.core.credentials import get_credential

    if not config.alert_channel:
        return

    try:
        creds = get_credential(db, str(config.workspace_id), "slack")
        if not creds:
            return
        token = creds.get("token") or creds.get("bot_token", "")
        if not token:
            return
        from app.runtime.integrations.slack import post_message
        post_message(token=token, channel=config.alert_channel, text=text_msg)
    except Exception:
        pass  # never crash ingest on Slack failure


def _check_spend_budget(db: Session, workspace_id: str, config: GuardConfig | None = None) -> None:
    """Log a warning (and send Slack alert) if any active budget has exceeded alert_threshold_pct."""
    import uuid
    from sqlalchemy import func

    now = _now()
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return

    budgets = (
        db.query(GuardSpendBudget)
        .filter(GuardSpendBudget.workspace_id == ws_uuid)
        .all()
    )
    if not budgets:
        return

    monthly_cost = (
        db.query(func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0))
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= period_start,
        )
        .scalar()
    ) or 0.0

    cfg = config or db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()

    for budget in budgets:
        threshold_usd = budget.monthly_limit_usd * (budget.alert_threshold_pct / 100.0)
        if monthly_cost >= threshold_usd and budget.monthly_limit_usd > 0:
            pct_used = (monthly_cost / budget.monthly_limit_usd) * 100
            # Only alert once per 5% increment to avoid spam
            pct_bucket = int(pct_used // 5) * 5
            last_alerted = getattr(budget, "last_alert_pct_bucket", None)
            if last_alerted is not None and pct_bucket <= last_alerted:
                continue
            try:
                budget.last_alert_pct_bucket = pct_bucket
                db.commit()
            except Exception:
                db.rollback()

            scope = f"user={budget.clerk_user_id}" if budget.clerk_user_id else "workspace-wide"
            log.info(
                "guard.spend_alert",
                workspace_id=workspace_id,
                scope=scope,
                monthly_cost_usd=round(monthly_cost, 4),
                threshold_usd=round(threshold_usd, 4),
                alert_threshold_pct=budget.alert_threshold_pct,
                budget_usd=budget.monthly_limit_usd,
            )
            if cfg and cfg.notify_on_budget:
                who = f"user={budget.clerk_user_id}" if budget.clerk_user_id else "workspace-wide"
                msg = (
                    f"\u26a0\ufe0f *Guard spend alert* ({who}): "
                    f"${monthly_cost:.2f} of ${budget.monthly_limit_usd:.2f} used ({round(pct_used)}%) \u2014 "
                    f"alert threshold {budget.alert_threshold_pct}% reached"
                )
                _send_guard_slack(db, cfg, msg)
