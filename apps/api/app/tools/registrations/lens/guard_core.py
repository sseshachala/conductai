"""Lens tool registrations — guard_core domain.

Split from the flat lens.py on 2026-08-29 to keep each file focused on
one KPI/read/action domain. See lens/_shared.py for common constants and
helpers; see lens/__init__.py for the composition root.

Do not import from other domain files — depend only on _shared.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text as sa_text, func as sa_func, or_ as sa_or

from app.tools.types import ToolDef
from app.tools.registrations.lens._shared import (
    _actor_impl,
    _window_start,
    _LIMIT,
    _DECISION,
    _TS_SINCE,
    _TS_UNTIL,
    _RULE_ID,
    _DAYS_WINDOW,
    _TIME_WINDOW,
    _READ_ONLY,
    _READ_ONLY_OPEN_WORLD,
    _LENS_TAGS,
    _ACTOR_TAGS
)
from app.modules.guard.routers.spend import _get_spend_summary_inner, _org_ws_subquery
from app.modules.guard.embedding import embedding_client_for_workspace
from app.modules.guard.models import (
    GuardAuditEvent,
    GuardConfig,
    GuardSpendBudget,
)

# ── Migrated from Executor (epic #1655 PR 8/9) ─────────────────────────
MIN_SIMILARITY_SCORE = 0.3  # Distance ceiling for pgvector semantic search (moved from Executor).

def get_spend_summary(ctx, month: str | None = None):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        summary = _get_spend_summary_inner(db, ctx.workspace_id, month)
        return {
            "events_today":       summary.events_today,
            "blocked_today":      summary.blocked_today,
            "total_cost_usd":     round(summary.total_cost_usd, 4),
            "active_developers":  summary.active_developers,
            "tokens_saved_today": summary.tokens_saved_today,
            "sessions":           summary.sessions,
            "by_ai_tool":  [{"tool": t.ai_tool,  "cost_usd": round(t.cost_usd, 4)} for t in summary.by_ai_tool],
            "by_developer": [{"email": d.email, "cost_usd": round(d.cost_usd, 4)} for d in summary.by_developer],
        }
    finally:
        db.close()


def get_recent_events(ctx, limit: int = 20, decision: str | None = None, since: str | None = None, until: str | None = None, rule_id: str | None = None,):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        from datetime import datetime, timezone
        if decision:
            decision = {"block": "blocked", "warn": "warned", "audit": "audited", "allow": "allowed"}.get(decision, decision)
        # Accept "today" as a since shortcut (mirrors _tool_list_pending_approvals)
        if since and since.strip().lower() == "today":
            since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        if until and until.strip().lower() == "today":
            until = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=999999)
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        q = db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id.in_(org_ws))
        if decision:
            q = q.filter(GuardAuditEvent.decision == decision)
        if rule_id:
            q = q.filter(GuardAuditEvent.rule_id == rule_id)
        if since:
            q = q.filter(GuardAuditEvent.ts >= since)
        if until:
            q = q.filter(GuardAuditEvent.ts <= until)
        rows = q.order_by(GuardAuditEvent.ts.desc()).limit(min(limit, 100)).all()
        return [
            {"id": str(e.id), "ts": e.ts.isoformat(), "decision": e.decision, "user_email": e.user_email,
             "ai_tool": e.ai_tool, "rule_id": e.rule_id, "tool_call": e.tool_call}
            for e in rows
        ]
    finally:
        db.close()


def get_sessions(ctx, limit: int = 20):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        from app.modules.guard.models import GuardSession
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        rows = (
            db.query(GuardSession)
            .filter(GuardSession.workspace_id.in_(org_ws))
            .order_by(GuardSession.started_at.desc())
            .limit(min(limit, 100))
            .all()
        )
        return [
            {"id": str(r.id), "user_email": r.user_email, "ai_tool": r.ai_tool,
             "started_at": r.started_at.isoformat() if r.started_at else None,
             "total_cost_usd": round(r.total_cost_usd, 4)}
            for r in rows
        ]
    finally:
        db.close()


def get_event_count(ctx, decision: str | None = None, since: str | None = None, until: str | None = None, rule_id: str | None = None,):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        """Exact COUNT of audit events matching filters — use for 'how many X' questions."""
        if decision:
            decision = {"block": "blocked", "warn": "warned", "audit": "audited", "allow": "allowed"}.get(decision, decision)
        from sqlalchemy import func as sa_func
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        q = db.query(sa_func.count(GuardAuditEvent.id)).filter(
            GuardAuditEvent.workspace_id.in_(org_ws)
        )
        if decision:
            q = q.filter(GuardAuditEvent.decision == decision)
        if rule_id:
            q = q.filter(GuardAuditEvent.rule_id == rule_id)
        if since:
            q = q.filter(GuardAuditEvent.ts >= since)
        if until:
            q = q.filter(GuardAuditEvent.ts <= until)
        return {"count": int(q.scalar() or 0), "decision": decision, "since": since, "until": until}
    finally:
        db.close()


def search_memory(ctx, q: str, limit: int = 5):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        client = embedding_client_for_workspace(db, ctx.workspace_id)
        if not client:
            return {"error": "Embedding service not configured for this workspace"}
        embedding = client.embed(q[:2000])
        rows = db.execute(
            sa_text(
                "SELECT tsm.id, tsm.developer_email, tsm.light_summary, tsm.topic_tags, "
                "tsm.repo_full_name, tsm.created_at, "
                "(tsm.embedding <=> CAST(:vec AS vector)) AS distance "
                "FROM team_session_memory tsm "
                "WHERE tsm.workspace_id = :workspace_id "
                "  AND tsm.visibility = 'team' AND tsm.embedding IS NOT NULL "
                "ORDER BY distance ASC LIMIT :limit"
            ),
            {"workspace_id": ctx.workspace_id, "vec": str(embedding), "limit": min(limit, 20)},
        ).fetchall()
        return [
            {"id": str(r.id), "developer_email": r.developer_email, "summary": r.light_summary,
             "topic_tags": r.topic_tags or [], "repo": r.repo_full_name,
             "created_at": r.created_at.isoformat(), "score": round(1 - r.distance, 3)}
            for r in rows
            if (1 - r.distance) >= MIN_SIMILARITY_SCORE
        ]
    finally:
        db.close()


def search_sessions(ctx, q: str, limit: int = 5):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        from app.modules.guard.models import SessionReport
        client = embedding_client_for_workspace(db, ctx.workspace_id)
        if not client:
            return {"error": "Embedding service not configured for this workspace"}
        embedding = client.embed(q[:2000])
        rows = db.execute(
            sa_text(
                "SELECT sr.id, sr.developer_email, sr.ai_tool, sr.report_md, sr.created_at, "
                "(sr.embedding <=> CAST(:vec AS vector)) AS distance "
                "FROM session_reports sr "
                "WHERE sr.workspace_id = :workspace_id AND sr.embedding IS NOT NULL "
                "ORDER BY distance ASC LIMIT :limit"
            ),
            {"workspace_id": ctx.workspace_id, "vec": str(embedding), "limit": min(limit, 20)},
        ).fetchall()
        return [
            {"id": str(r.id), "developer_email": r.developer_email, "ai_tool": r.ai_tool,
             "summary": (r.report_md or "")[:500], "created_at": r.created_at.isoformat(),
             "score": round(1 - r.distance, 3)}
            for r in rows
            if (1 - r.distance) >= MIN_SIMILARITY_SCORE
        ]
    finally:
        db.close()


def get_team_memory_feed(ctx, limit: int = 20):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        """Recent team memory entries — no embedding needed."""
        rows = db.execute(
            sa_text(
                "SELECT id, developer_email, light_summary, topic_tags, repo_full_name, created_at "
                "FROM team_session_memory "
                "WHERE workspace_id = :workspace_id AND visibility = 'team' "
                "ORDER BY created_at DESC LIMIT :limit"
            ),
            {"workspace_id": ctx.workspace_id, "limit": min(limit, 50)},
        ).fetchall()
        return [
            {"id": str(r.id), "developer_email": r.developer_email, "summary": r.light_summary,
             "topic_tags": r.topic_tags or [], "repo": r.repo_full_name,
             "created_at": r.created_at.isoformat()}
            for r in rows
        ]
    finally:
        db.close()


def get_session_reports_feed(ctx, limit: int = 20):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        """Recent session reports — no embedding needed."""
        rows = db.execute(
            sa_text(
                "SELECT id, developer_email, ai_tool, report_md, created_at "
                "FROM session_reports "
                "WHERE workspace_id = :workspace_id "
                "ORDER BY created_at DESC LIMIT :limit"
            ),
            {"workspace_id": ctx.workspace_id, "limit": min(limit, 50)},
        ).fetchall()
        return [
            {"id": str(r.id), "developer_email": r.developer_email, "ai_tool": r.ai_tool,
             "summary": (r.report_md or "")[:500], "created_at": r.created_at.isoformat()}
            for r in rows
        ]
    finally:
        db.close()


def search_knowledge(ctx, q: str, kind: str | None = None, limit: int = 10):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        """Semantic search across all Guard knowledge — audit events, rules, discovered agents."""
        client = embedding_client_for_workspace(db, ctx.workspace_id)
        if not client:
            return {"error": "Embedding service not configured"}
        embedding = client.embed(q[:2000])
        kind_filter = "AND gki.source_kind = :kind" if kind else ""
        rows = db.execute(
            sa_text(
                f"SELECT gki.source_kind, gki.source_id, gki.canonical_text, gki.metadata, "
                f"(gki.embedding <=> CAST(:vec AS vector)) AS distance "
                f"FROM guard_knowledge_index gki "
                f"WHERE gki.workspace_id = CAST(:workspace_id AS uuid) AND gki.embedding IS NOT NULL "
                f"{kind_filter} "
                f"ORDER BY distance ASC LIMIT :limit"
            ),
            {
                "workspace_id": ctx.workspace_id,
                "vec": str(embedding),
                "limit": min(limit, 50),
                "kind": kind,
            },
        ).fetchall()
        return [
            {
                "source_kind": r.source_kind,
                "source_id": r.source_id,
                "text": r.canonical_text,
                "metadata": r.metadata,
                "score": round(1 - r.distance, 3),
            }
            for r in rows
        ]
    finally:
        db.close()


def get_guard_config(ctx):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        ws_uuid = uuid.UUID(ctx.workspace_id)
        cfg = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
        if not cfg:
            return {"configured": False}
        return {
            "enforcement_mode": cfg.enforcement_mode,
            "fail_mode": getattr(cfg, "fail_mode", "fail_open"),
            "advisory_mode": cfg.advisory_mode,
            "notify_on_block": cfg.notify_on_block,
            "notify_on_budget": cfg.notify_on_budget,
            "deny_on_error": getattr(cfg, "deny_on_error", False),
            "persona": cfg.persona,
        }
    finally:
        db.close()


def get_budgets(ctx):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        from app.modules.guard.models import GuardSession
        ws_uuid = uuid.UUID(ctx.workspace_id)
        rows = db.query(GuardSpendBudget).filter(
            GuardSpendBudget.workspace_id == ws_uuid
        ).all()

        # Build clerk_user_id → email map from sessions
        clerk_ids = [r.clerk_user_id for r in rows if r.clerk_user_id]
        email_map: dict[str, str] = {}
        if clerk_ids:
            sessions = (
                db.query(GuardSession.clerk_user_id, GuardSession.user_email)
                .filter(
                    GuardSession.workspace_id == ws_uuid,
                    GuardSession.clerk_user_id.in_(clerk_ids),
                    GuardSession.user_email.isnot(None),
                )
                .distinct()
                .all()
            )
            email_map = {s.clerk_user_id: s.user_email for s in sessions}

        return [
            {
                "scope": "workspace" if r.clerk_user_id is None else "developer",
                "email": None if r.clerk_user_id is None else email_map.get(r.clerk_user_id, r.clerk_user_id),
                "monthly_limit_usd": r.monthly_limit_usd,
                "hard_limit_usd": r.hard_limit_usd,
                "alert_threshold_pct": r.alert_threshold_pct,
                "default_per_developer_usd": r.default_per_developer_usd,
            }
            for r in rows
        ]
    finally:
        db.close()


def get_correlated_events(ctx, decision: str = "blocked", since: str | None = None, until: str | None = None, limit: int = 50):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        from app.modules.guard.models import GuardSession as _GS
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        q = (
            db.query(GuardAuditEvent, _GS)
            .outerjoin(_GS, GuardAuditEvent.session_id == _GS.id)
            .filter(GuardAuditEvent.workspace_id.in_(org_ws))
            .filter(GuardAuditEvent.decision == decision)
        )
        if since:
            q = q.filter(GuardAuditEvent.ts >= since)
        if until:
            q = q.filter(GuardAuditEvent.ts <= until)
        rows = q.order_by(GuardAuditEvent.ts.desc()).limit(min(limit, 100)).all()
        sessions: dict = {}
        ungrouped = []
        for event, session in rows:
            evt = {"id": str(event.id), "ts": event.ts.isoformat(), "decision": event.decision,
                   "rule_id": event.rule_id, "ai_tool": event.ai_tool, "user_email": event.user_email}
            if session:
                sid = str(session.id)
                if sid not in sessions:
                    sessions[sid] = {"session_id": sid, "user_email": session.user_email,
                                     "ai_tool": session.ai_tool,
                                     "started_at": session.started_at.isoformat() if session.started_at else None,
                                     "events": []}
                sessions[sid]["events"].append(evt)
            else:
                ungrouped.append(evt)
        return {"sessions": list(sessions.values()), "ungrouped": ungrouped, "total": len(rows)}
    finally:
        db.close()


def get_savings_summary(ctx):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        from app.modules.guard.routers.savings import _build_summary, _EMPTY_SUMMARY
        try:
            result = _build_summary(db, ctx.workspace_id)
        except Exception:
            result = _EMPTY_SUMMARY
        t = result.team_total
        total = t.rtk_saved_tokens + t.booster_saved_tokens
        usd = t.rtk_saved_usd + t.booster_saved_usd
        members = [
            {
                "email": m.member_email,
                "rtk_saved_tokens": m.rtk_saved_tokens,
                "booster_saved_tokens": m.booster_saved_tokens,
            }
            for m in result.by_member
        ]
        return {"total_tokens_saved": total, "total_cost_saved_usd": round(usd, 4), "by_member": members}
    finally:
        db.close()


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_spend_summary",
        description="Guard workspace spend summary — events today, cost, active devs, tokens saved. Optional month filter (YYYY-MM).",
        input_schema={"type": "object", "properties": {"month": {"type": "string"}}, "required": []},
        impl=get_spend_summary,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_recent_events",
        description="Recent Guard audit events, optionally filtered by decision, rule_id, time range.",
        input_schema={
            "type": "object",
            "properties": {
                "limit": _LIMIT, "decision": _DECISION,
                "since": _TS_SINCE, "until": _TS_UNTIL, "rule_id": _RULE_ID,
            },
            "required": [],
        },
        impl=get_recent_events,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_sessions",
        description="Recent Guard sessions (agent transcripts) for the workspace.",
        input_schema={"type": "object", "properties": {"limit": _LIMIT}, "required": []},
        impl=get_sessions,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_event_count",
        description="Exact COUNT of audit events matching filters. Use for 'how many X' questions.",
        input_schema={
            "type": "object",
            "properties": {
                "decision": _DECISION, "since": _TS_SINCE,
                "until": _TS_UNTIL, "rule_id": _RULE_ID,
            },
            "required": [],
        },
        impl=get_event_count,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="search_memory",
        description="Semantic search across team session memory (past agent work summaries).",
        input_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}, "limit": _LIMIT},
            "required": ["q"],
        },
        impl=search_memory,
        annotations=_READ_ONLY_OPEN_WORLD,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="search_sessions",
        description="Semantic search across session reports (Guard-generated agent transcripts).",
        input_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}, "limit": _LIMIT},
            "required": ["q"],
        },
        impl=search_sessions,
        annotations=_READ_ONLY_OPEN_WORLD,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_team_memory_feed",
        description="Recent team memory entries. No embeddings required.",
        input_schema={"type": "object", "properties": {"limit": _LIMIT}, "required": []},
        impl=get_team_memory_feed,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_session_reports_feed",
        description="Recent session reports. No embeddings required.",
        input_schema={"type": "object", "properties": {"limit": _LIMIT}, "required": []},
        impl=get_session_reports_feed,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="search_knowledge",
        description="Semantic search across all Guard knowledge (audit events, rules, discovered agents). Optional kind filter.",
        input_schema={
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "kind": {"type": "string", "description": "Optional source_kind filter"},
                "limit": _LIMIT,
            },
            "required": ["q"],
        },
        impl=search_knowledge,
        annotations=_READ_ONLY_OPEN_WORLD,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_guard_config",
        description="Workspace Guard config — enforcement mode, fail mode, persona, notification settings.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_guard_config,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_budgets",
        description="Workspace and per-developer spend budgets.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_budgets,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_correlated_events",
        description="Guard audit events grouped by session. Defaults to blocked events. Time-bounded via since/until.",
        input_schema={
            "type": "object",
            "properties": {
                "decision": _DECISION, "since": _TS_SINCE,
                "until": _TS_UNTIL, "limit": _LIMIT,
            },
            "required": [],
        },
        impl=get_correlated_events,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_savings_summary",
        description="Team token/cost savings from RTK + Booster.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_savings_summary,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
