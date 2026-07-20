"""GLens tool executor — maps tool names to DB queries, called inside the agent loop."""
import json
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.modules.guard.models import (
    GuardAuditEvent,
    GuardConfig,
    GuardSpendBudget,
    WorkspaceCustomRule,
    WorkspaceSkillPack,
    SkillPack,
    DiscoveredAgent,
    WorkspaceSigningKey,
)
from app.modules.guard.routers.spend import _get_spend_summary_inner, _org_ws_subquery
from app.modules.guard.embedding import embedding_client_for_workspace

log = structlog.get_logger(__name__)


class Executor:
    MIN_SIMILARITY_SCORE = 0.3

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
        if decision:
            decision = {"block": "blocked", "warn": "warned", "audit": "audited", "allow": "allowed"}.get(decision, decision)
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
        if decision:
            decision = {"block": "blocked", "warn": "warned", "audit": "audited", "allow": "allowed"}.get(decision, decision)
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
            if (1 - r.distance) >= self.MIN_SIMILARITY_SCORE
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
            if (1 - r.distance) >= self.MIN_SIMILARITY_SCORE
        ]

    def _tool_get_team_memory_feed(self, limit: int = 20):
        """Recent team memory entries — no embedding needed."""
        rows = self.db.execute(
            sa_text(
                "SELECT id, developer_email, light_summary, topic_tags, repo_full_name, created_at "
                "FROM team_session_memory "
                "WHERE workspace_id = :workspace_id AND visibility = 'team' "
                "ORDER BY created_at DESC LIMIT :limit"
            ),
            {"workspace_id": self.workspace_id, "limit": min(limit, 50)},
        ).fetchall()
        return [
            {"id": str(r.id), "developer_email": r.developer_email, "summary": r.light_summary,
             "topic_tags": r.topic_tags or [], "repo": r.repo_full_name,
             "created_at": r.created_at.isoformat()}
            for r in rows
        ]

    def _tool_get_session_reports_feed(self, limit: int = 20):
        """Recent session reports — no embedding needed."""
        rows = self.db.execute(
            sa_text(
                "SELECT id, developer_email, ai_tool, report_md, created_at "
                "FROM session_reports "
                "WHERE workspace_id = :workspace_id "
                "ORDER BY created_at DESC LIMIT :limit"
            ),
            {"workspace_id": self.workspace_id, "limit": min(limit, 50)},
        ).fetchall()
        return [
            {"id": str(r.id), "developer_email": r.developer_email, "ai_tool": r.ai_tool,
             "summary": (r.report_md or "")[:500], "created_at": r.created_at.isoformat()}
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
        from app.modules.guard.models import GuardSession
        ws_uuid = uuid.UUID(self.workspace_id)
        rows = self.db.query(GuardSpendBudget).filter(
            GuardSpendBudget.workspace_id == ws_uuid
        ).all()

        # Build clerk_user_id → email map from sessions
        clerk_ids = [r.clerk_user_id for r in rows if r.clerk_user_id]
        email_map: dict[str, str] = {}
        if clerk_ids:
            sessions = (
                self.db.query(GuardSession.clerk_user_id, GuardSession.user_email)
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

    # ── Discovery ─────────────────────────────────────────────────────────────

    def _tool_get_discovery_summary(self):
        ws_uuid = uuid.UUID(self.workspace_id)
        agents = self.db.query(DiscoveredAgent).filter(
            DiscoveredAgent.workspace_id == ws_uuid
        ).all()

        total = len(agents)
        under_guard = sum(1 for a in agents if a.under_guard)

        by_framework: dict[str, int] = {}
        for a in agents:
            fw = a.framework or "unknown"
            by_framework[fw] = by_framework.get(fw, 0) + 1

        def _risk_level(score: int | None) -> str:
            if score is None:
                return "Unknown"
            if score >= 70:
                return "High"
            if score >= 40:
                return "Medium"
            return "Low"

        high_risk = [
            {"name": a.name, "framework": a.framework, "risk_score": a.risk_score,
             "under_guard": a.under_guard, "location": a.location}
            for a in agents if (a.risk_score or 0) >= 70
        ]

        return {
            "total": total,
            "under_guard": under_guard,
            "missing": total - under_guard,
            "coverage_pct": round(under_guard / total * 100) if total else 0,
            "by_framework": [{"framework": fw, "count": cnt} for fw, cnt in sorted(by_framework.items())],
            "high_risk": high_risk,
            "agents": [
                {
                    "name": a.name,
                    "framework": a.framework,
                    "source": a.source,
                    "location": a.location,
                    "risk_score": a.risk_score,
                    "risk_level": _risk_level(a.risk_score),
                    "under_guard": a.under_guard,
                    "proxy_routed": a.proxy_routed,
                    "last_seen_at": a.last_seen_at.isoformat() if a.last_seen_at else None,
                }
                for a in agents
            ],
        }

    # ── Compliance ────────────────────────────────────────────────────────────

    def _tool_get_compliance_status(self):
        """Replicates /guard/verify/evidence DB logic without an HTTP round-trip."""
        from datetime import timedelta
        import hashlib

        ws_uuid = uuid.UUID(self.workspace_id)
        org_ws = _org_ws_subquery(self.db, self.workspace_id)
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=24)

        gc = self.db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
        signing_key = self.db.query(WorkspaceSigningKey).filter(
            WorkspaceSigningKey.workspace_id == ws_uuid
        ).first()

        policy_count = (
            self.db.query(WorkspaceCustomRule)
            .filter(WorkspaceCustomRule.workspace_id.in_(org_ws))
            .count()
            + self.db.query(WorkspaceSkillPack)
            .filter(WorkspaceSkillPack.workspace_id.in_(org_ws))
            .count()
        )

        events_24h = (
            self.db.query(GuardAuditEvent)
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.ts >= since,
            )
            .count()
        )

        blocked_24h = (
            self.db.query(GuardAuditEvent)
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.ts >= since,
                GuardAuditEvent.decision == "blocked",
            )
            .count()
        )

        # Score computation (mirrors verify.py)
        score = 0
        guard_active = bool(gc and gc.enforcement_mode in ("block", "warn", "audit"))

        if gc:
            if gc.enforcement_mode == "block":
                score += 30
            elif gc.enforcement_mode == "warn":
                score += 15
            elif gc.enforcement_mode == "audit":
                score += 5
            if gc.fail_mode == "fail_closed":
                score += 15
            if gc.deny_on_error:
                score += 10

        if signing_key:
            score += 15

        if policy_count >= 5:
            score += 20
        elif policy_count > 0:
            score += 10

        if events_24h > 0:
            score += 10

        fail_closed = gc and gc.fail_mode == "fail_closed"

        _CONTROLS = [
            ("ASI-01", "Prompt Injection",        "PreToolUse hook intercepts before LLM call"),
            ("ASI-02", "Insecure Tool Use",       "Guard proxy enforces tool-use policies"),
            ("ASI-03", "Excessive Agency",        "Turn budgets + max_cost_usd caps"),
            ("ASI-04", "Unauthorized Escalation", "RBAC + require_permission() on all endpoints"),
            ("ASI-05", "Trust Boundary Violation","All LLM traffic routed through Guard proxy"),
            ("ASI-06", "Insufficient Logging",    "guard_audit_events with SHA-256 hash chain"),
            ("ASI-07", "Insecure Identity",       "agent_role_id + member tokens per agent"),
            ("ASI-08", "Policy Bypass",           "fail_mode=fail_closed blocks on Guard outage"),
            ("ASI-09", "Supply Chain Integrity",  "Signed policies (signing_key)"),
            ("ASI-10", "Behavioral Anomaly",      "Session scanning + violations_count tracking"),
        ]

        def _status(asi: str) -> str:
            if asi in ("ASI-01", "ASI-02", "ASI-05"):
                return "active" if guard_active else "missing"
            if asi in ("ASI-03", "ASI-04"):
                return "active"
            if asi == "ASI-06":
                if guard_active and events_24h > 0:
                    return "active"
                return "partial" if guard_active else "missing"
            if asi == "ASI-07":
                return "partial"
            if asi == "ASI-08":
                return "active" if fail_closed else "partial"
            if asi == "ASI-09":
                return "active" if signing_key else "missing"
            if asi == "ASI-10":
                return "partial"
            return "missing"

        controls = [
            {"control_id": asi, "name": name, "status": _status(asi), "conduct_enforcement": enforcement}
            for asi, name, enforcement in _CONTROLS
        ]

        active_count = sum(1 for c in controls if c["status"] == "active")
        coverage_pct = round(active_count / len(controls) * 100)

        def _grade(s: int) -> str:
            for threshold, letter in [(85, "A"), (65, "B"), (45, "C"), (25, "D"), (0, "F")]:
                if s >= threshold:
                    return letter
            return "F"

        return {
            "grade": _grade(score),
            "score": score,
            "coverage_pct": coverage_pct,
            "controls": controls,
            "events_24h": {"total": events_24h, "blocked": blocked_24h},
        }

    # ── Governance ────────────────────────────────────────────────────────────

    def _tool_get_governance_kpis(self):
        from datetime import timedelta
        from sqlalchemy import func as sa_func

        ws_uuid = uuid.UUID(self.workspace_id)
        org_ws = _org_ws_subquery(self.db, self.workspace_id)
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        base_q = self.db.query(GuardAuditEvent).filter(
            GuardAuditEvent.workspace_id.in_(org_ws)
        )

        events_today = base_q.filter(GuardAuditEvent.ts >= today_start).count()

        blocked_today = base_q.filter(
            GuardAuditEvent.ts >= today_start,
            GuardAuditEvent.decision == "blocked",
        ).count()

        active_developers_today = (
            self.db.query(sa_func.count(sa_func.distinct(GuardAuditEvent.user_email)))
            .filter(
                GuardAuditEvent.workspace_id.in_(org_ws),
                GuardAuditEvent.ts >= today_start,
                GuardAuditEvent.user_email.isnot(None),
            )
            .scalar() or 0
        )

        blocks_mtd = base_q.filter(
            GuardAuditEvent.ts >= month_start,
            GuardAuditEvent.decision == "blocked",
        ).count()

        # Approximate risk avoided: $0.01 per blocked event (no cost field on blocked events)
        risk_avoided_usd_mtd = round(blocks_mtd * 0.01, 2)

        return {
            "events_today": events_today,
            "blocked_today": blocked_today,
            "active_developers_today": int(active_developers_today),
            "blocks_mtd": blocks_mtd,
            "risk_avoided_usd_mtd": risk_avoided_usd_mtd,
        }

    def _tool_get_framework_coverage(self):
        from sqlalchemy import func as sa_func

        org_ws = _org_ws_subquery(self.db, self.workspace_id)

        _PACK_TO_FRAMEWORK = {
            "conduct-owasp":    "OWASP",
            "conduct-soc2":     "SOC2",
            "conduct-hipaa":    "HIPAA",
            "conduct-pci-dss":  "PCI_DSS",
            "conduct-base":     "Base",
            "conduct-iso42001": "ISO_42001",
            "conduct-gdpr":     "GDPR",
            "conduct-nist":     "NIST",
            "conduct-nis2":     "NIS2",
            "conduct-dora":     "DORA",
        }

        # Installed packs for this workspace (org-scoped)
        installed_wsps = (
            self.db.query(WorkspaceSkillPack)
            .filter(WorkspaceSkillPack.workspace_id.in_(org_ws))
            .all()
        )

        # Collect unique pack slugs installed
        seen_slugs: set[str] = set()
        wsp_by_slug: dict[str, WorkspaceSkillPack] = {}
        for wsp in installed_wsps:
            if wsp.pack_slug not in seen_slugs:
                seen_slugs.add(wsp.pack_slug)
                wsp_by_slug[wsp.pack_slug] = wsp

        # Fetch rules counts from SkillPack catalog (latest version per slug)
        rules_count_by_slug: dict[str, int] = {}
        if seen_slugs:
            catalog_rows = (
                self.db.query(SkillPack.slug, SkillPack.rules)
                .filter(SkillPack.slug.in_(list(seen_slugs)))
                .all()
            )
            # Sum rules across all versions (or just take any — rules are per slug+version)
            for slug, rules in catalog_rows:
                cnt = len(rules) if isinstance(rules, list) else 0
                rules_count_by_slug[slug] = max(rules_count_by_slug.get(slug, 0), cnt)

        frameworks = [
            {
                "pack_slug": slug,
                "framework": _PACK_TO_FRAMEWORK.get(slug, slug),
                "rules_count": rules_count_by_slug.get(slug, 0),
                "installed_at": wsp_by_slug[slug].installed_at.isoformat()
                    if wsp_by_slug[slug].installed_at else None,
            }
            for slug in sorted(seen_slugs)
        ]

        return {
            "installed_count": len(frameworks),
            "frameworks": frameworks,
        }

    def _tool_get_correlated_events(self, decision: str = "blocked", since: str | None = None, until: str | None = None, limit: int = 50):
        from app.modules.guard.models import GuardSession as _GS
        org_ws = _org_ws_subquery(self.db, self.workspace_id)
        q = (
            self.db.query(GuardAuditEvent, _GS)
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

    def _tool_get_savings_summary(self):
        from app.modules.guard.routers.savings import _build_summary, _EMPTY_SUMMARY
        try:
            result = _build_summary(self.db, self.workspace_id)
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

    def _tool_get_governance_narrative(self):
        from app.routers.governance import get_narrative as _get_narrative, _compute_framework_coverage
        try:
            result = _get_narrative(db=self.db, workspace_id=self.workspace_id)
            return {"paragraph": result.paragraph, "source": result.source}
        except Exception as e:
            return {"paragraph": f"Narrative unavailable: {e}", "source": "error"}

    def _tool_get_recent_governance_events(self, limit: int = 15, decision: str | None = None, since: str | None = None, until: str | None = None):
        if decision:
            decision = {"block": "blocked", "warn": "warned", "audit": "audited", "allow": "allowed"}.get(decision, decision)
        # when a full date range is given and no explicit limit, fetch all events in that window
        if since and until and limit == 15:
            limit = 500
        org_ws = _org_ws_subquery(self.db, self.workspace_id)
        q = self.db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id.in_(org_ws))
        if decision:
            q = q.filter(GuardAuditEvent.decision == decision)
        if since:
            q = q.filter(GuardAuditEvent.ts >= since)
        if until:
            q = q.filter(GuardAuditEvent.ts <= until)
        rows = (
            q.order_by(GuardAuditEvent.ts.desc())
            .limit(min(limit, 100))
            .all()
        )
        return [
            {
                "id": str(e.id),
                "ts": e.ts.isoformat(),
                "decision": e.decision,
                "rule_id": e.rule_id,
                "ai_tool": e.ai_tool,
                "user_email": e.user_email,
            }
            for e in rows
        ]
