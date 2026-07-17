"""GLens tool executor — maps tool names to DB queries, called inside the agent loop."""
import json
import uuid

import structlog
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.modules.guard.models import GuardAuditEvent, GuardConfig, GuardSpendBudget, WorkspaceCustomRule
from app.modules.guard.routers.spend import _get_spend_summary_inner, _org_ws_subquery
from app.modules.guard.embedding import embedding_client_for_workspace

log = structlog.get_logger(__name__)


class Executor:
    def __init__(self, db: Session, workspace_id: str):
        self.db = db
        self.workspace_id = workspace_id

    def call(self, name: str, arguments: str) -> str:
        args = json.loads(arguments) if arguments else {}
        fn = getattr(self, f"_tool_{name}", None)
        if not fn:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            return json.dumps(fn(**args))
        except Exception as e:
            log.warning("glens.executor.error", tool=name, error=str(e))
            return json.dumps({"error": str(e)})

    # ── Spend / events ────────────────────────────────────────────────────────

    def _tool_get_spend_summary(self, month: str | None = None):
        summary = _get_spend_summary_inner(self.db, self.workspace_id, month)
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

    def _tool_get_recent_events(
        self,
        limit: int = 20,
        decision: str | None = None,
        since: str | None = None,
        until: str | None = None,
        rule_id: str | None = None,
    ):
        org_ws = _org_ws_subquery(self.db, self.workspace_id)
        q = self.db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id.in_(org_ws))
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
            {"ts": e.ts.isoformat(), "decision": e.decision, "user_email": e.user_email,
             "ai_tool": e.ai_tool, "rule_id": e.rule_id, "tool_name": e.tool_name}
            for e in rows
        ]

    def _tool_get_sessions(self, limit: int = 20):
        from app.modules.guard.models import GuardSession
        org_ws = _org_ws_subquery(self.db, self.workspace_id)
        rows = (
            self.db.query(GuardSession)
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

    def _tool_get_event_count(
        self,
        decision: str | None = None,
        since: str | None = None,
        until: str | None = None,
        rule_id: str | None = None,
    ):
        """Exact COUNT of audit events matching filters — use for 'how many X' questions."""
        from sqlalchemy import func as sa_func
        org_ws = _org_ws_subquery(self.db, self.workspace_id)
        q = self.db.query(sa_func.count(GuardAuditEvent.id)).filter(
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

    # ── Memory / session semantic search ─────────────────────────────────────

    def _tool_search_memory(self, q: str, limit: int = 5):
        client = embedding_client_for_workspace(self.db, self.workspace_id)
        if not client:
            return {"error": "Embedding service not configured for this workspace"}
        embedding = client.embed(q[:2000])
        rows = self.db.execute(
            sa_text(
                "SELECT tsm.id, tsm.developer_email, tsm.light_summary, tsm.topic_tags, "
                "tsm.repo_full_name, tsm.created_at, "
                "(tsm.embedding <=> CAST(:vec AS vector)) AS distance "
                "FROM team_session_memory tsm "
                "WHERE tsm.workspace_id = :workspace_id "
                "  AND tsm.visibility = 'team' AND tsm.embedding IS NOT NULL "
                "ORDER BY distance ASC LIMIT :limit"
            ),
            {"workspace_id": self.workspace_id, "vec": str(embedding), "limit": min(limit, 20)},
        ).fetchall()
        return [
            {"id": str(r.id), "developer_email": r.developer_email, "summary": r.light_summary,
             "topic_tags": r.topic_tags or [], "repo": r.repo_full_name,
             "created_at": r.created_at.isoformat(), "score": round(1 - r.distance, 3)}
            for r in rows
        ]

    def _tool_search_sessions(self, q: str, limit: int = 5):
        from app.modules.guard.models import SessionReport
        client = embedding_client_for_workspace(self.db, self.workspace_id)
        if not client:
            return {"error": "Embedding service not configured for this workspace"}
        embedding = client.embed(q[:2000])
        rows = self.db.execute(
            sa_text(
                "SELECT sr.id, sr.developer_email, sr.ai_tool, sr.report_md, sr.created_at, "
                "(sr.embedding <=> CAST(:vec AS vector)) AS distance "
                "FROM session_reports sr "
                "WHERE sr.workspace_id = :workspace_id AND sr.embedding IS NOT NULL "
                "ORDER BY distance ASC LIMIT :limit"
            ),
            {"workspace_id": self.workspace_id, "vec": str(embedding), "limit": min(limit, 20)},
        ).fetchall()
        return [
            {"id": str(r.id), "developer_email": r.developer_email, "ai_tool": r.ai_tool,
             "summary": (r.report_md or "")[:500], "created_at": r.created_at.isoformat(),
             "score": round(1 - r.distance, 3)}
            for r in rows
        ]

    # ── Policies ──────────────────────────────────────────────────────────────

    def _tool_list_policies(self):
        ws_uuid = uuid.UUID(self.workspace_id)
        rows = self.db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.workspace_id == ws_uuid
        ).all()
        return [
            {"rule_id": r.rule_id, "enabled": r.enabled, "persona": r.persona,
             "action": r.body.get("action"), "description": r.body.get("description"),
             "match_tool": r.body.get("match_tool"), "match_pattern": r.body.get("match_pattern"),
             "severity": r.body.get("severity", "medium")}
            for r in rows
        ]

    def _tool_get_policy(self, rule_id: str):
        ws_uuid = uuid.UUID(self.workspace_id)
        row = self.db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.workspace_id == ws_uuid,
            WorkspaceCustomRule.rule_id == rule_id,
        ).first()
        if not row:
            return {"error": f"Policy '{rule_id}' not found"}
        return {"rule_id": row.rule_id, "enabled": row.enabled, "persona": row.persona, **row.body}

    # ── Knowledge index ───────────────────────────────────────────────────────

    def _tool_search_knowledge(self, q: str, kind: str | None = None, limit: int = 10):
        """Semantic search across all Guard knowledge — audit events, rules, discovered agents."""
        client = embedding_client_for_workspace(self.db, self.workspace_id)
        if not client:
            return {"error": "Embedding service not configured"}
        embedding = client.embed(q[:2000])
        kind_filter = "AND gki.source_kind = :kind" if kind else ""
        rows = self.db.execute(
            sa_text(
                f"SELECT gki.source_kind, gki.source_id, gki.canonical_text, gki.metadata, "
                f"(gki.embedding <=> CAST(:vec AS vector)) AS distance "
                f"FROM guard_knowledge_index gki "
                f"WHERE gki.workspace_id = CAST(:workspace_id AS uuid) AND gki.embedding IS NOT NULL "
                f"{kind_filter} "
                f"ORDER BY distance ASC LIMIT :limit"
            ),
            {
                "workspace_id": self.workspace_id,
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

    # ── Guard config ──────────────────────────────────────────────────────────

    def _tool_get_guard_config(self):
        ws_uuid = uuid.UUID(self.workspace_id)
        cfg = self.db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
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

    # ── Spend budgets ─────────────────────────────────────────────────────────

    def _tool_get_budgets(self):
        ws_uuid = uuid.UUID(self.workspace_id)
        rows = self.db.query(GuardSpendBudget).filter(
            GuardSpendBudget.workspace_id == ws_uuid
        ).all()
        return [
            {
                "scope": "workspace" if r.clerk_user_id is None else "developer",
                "email": None if r.clerk_user_id is None else r.clerk_user_id,
                "monthly_limit_usd": r.monthly_limit_usd,
                "hard_limit_usd": r.hard_limit_usd,
                "alert_threshold_pct": r.alert_threshold_pct,
                "default_per_developer_usd": r.default_per_developer_usd,
            }
            for r in rows
        ]
