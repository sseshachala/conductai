"""Lens tool registrations — governance domain.

Split from the flat lens.py on 2026-08-29 to keep each file focused on
one KPI/read/action domain. See lens/_shared.py for common constants and
helpers; see lens/__init__.py for the composition root.

Do not import from other domain files — depend only on _shared.
"""
from __future__ import annotations

from app.tools.types import ToolDef
from app.tools.registrations.lens._shared import (
    _impl,
    _run,
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


# ── Free-function tool implementations ─────────────────────────────────
def _run_framework_coverage(workspace_id: str):
    from app.core.database import SessionLocal
    from app.routers.governance import _compute_framework_coverage
    db = SessionLocal()
    try:
        return _compute_framework_coverage(db, workspace_id)
    finally:
        db.close()

def get_governance_summary(ctx):
    """Full framework coverage matrix — installed + bonus + rules totals."""
    return _run_framework_coverage(ctx.workspace_id).model_dump()

def get_soc2_status(ctx, framework: str = "SOC2"):
    """Rollup for a single compliance framework. Defaults to SOC2. Returns
    installed status + rules + controls + recommended pack for uninstalled."""
    from app.routers.governance import RECOMMENDED_PACK
    result = _run_framework_coverage(ctx.workspace_id)
    fw = framework.upper()
    for row in result.installed:
        if row.framework == fw:
            return {"status": "installed", **row.model_dump()}
    for row in result.bonus:
        if row.framework == fw:
            return {"status": "bonus", **row.model_dump()}
    return {
        "status": "not_covered",
        "framework": fw,
        "rules_count": 0,
        "controls": [],
        "packs": [],
        "recommended_pack": RECOMMENDED_PACK.get(fw),
    }

def get_ai_rollout_status(ctx):
    """AI rollout instructions published for the workspace — published flag,
    content length, version, last update, publisher."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.workspace_instructions import WorkspaceInstructions
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        row = db.query(WorkspaceInstructions).filter(
            WorkspaceInstructions.workspace_id == ws_uuid
        ).first()
        if row is None:
            return {
                "published": False,
                "content_length": 0,
                "version": None,
                "updated_at": None,
                "updated_by": None,
            }
        return {
            "published": True,
            "content_length": len(row.content or ""),
            "version": row.version,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": row.updated_by,
        }
    finally:
        db.close()


# ── Migrated from Executor (epic #1655 PR 7/9) ─────────────────────────
def _grade(s: int) -> str:
    for threshold, letter in [(85, "A"), (65, "B"), (45, "C"), (25, "D"), (0, "F")]:
        if s >= threshold:
            return letter
    return "F"


def get_compliance_status(ctx):
    """Compliance posture — grade, score, ASI control statuses. Replicates
    /guard/verify/evidence DB logic. Migrated from
    Executor._tool_get_compliance_status (epic #1655)."""
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone
    from app.core.database import SessionLocal
    from app.modules.guard.models import (
        GuardAuditEvent, GuardConfig, WorkspaceCustomRule,
        WorkspaceSkillPack, WorkspaceSigningKey,
    )
    from app.modules.guard.routers.spend import _org_ws_subquery

    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=24)

        gc = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
        signing_key = db.query(WorkspaceSigningKey).filter(
            WorkspaceSigningKey.workspace_id == ws_uuid
        ).first()

        policy_count = (
            db.query(WorkspaceCustomRule).filter(WorkspaceCustomRule.workspace_id.in_(org_ws)).count()
            + db.query(WorkspaceSkillPack).filter(WorkspaceSkillPack.workspace_id.in_(org_ws)).count()
        )

        events_24h = (
            db.query(GuardAuditEvent)
            .filter(GuardAuditEvent.workspace_id == ws_uuid, GuardAuditEvent.ts >= since)
            .count()
        )
        blocked_24h = (
            db.query(GuardAuditEvent)
            .filter(GuardAuditEvent.workspace_id == ws_uuid,
                    GuardAuditEvent.ts >= since,
                    GuardAuditEvent.decision == "blocked")
            .count()
        )

        score = 0
        guard_active = bool(gc and gc.enforcement_mode in ("block", "warn", "audit"))
        if gc:
            if gc.enforcement_mode == "block": score += 30
            elif gc.enforcement_mode == "warn": score += 15
            elif gc.enforcement_mode == "audit": score += 5
            if gc.fail_mode == "fail_closed": score += 15
            if gc.deny_on_error: score += 10
        if signing_key: score += 15
        if policy_count >= 5: score += 20
        elif policy_count > 0: score += 10
        if events_24h > 0: score += 10

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
                if guard_active and events_24h > 0: return "active"
                return "partial" if guard_active else "missing"
            if asi == "ASI-07": return "partial"
            if asi == "ASI-08": return "active" if fail_closed else "partial"
            if asi == "ASI-09": return "active" if signing_key else "missing"
            if asi == "ASI-10": return "partial"
            return "missing"

        controls = [
            {"control_id": asi, "name": name, "status": _status(asi), "conduct_enforcement": enforcement}
            for asi, name, enforcement in _CONTROLS
        ]
        active_count = sum(1 for c in controls if c["status"] == "active")
        coverage_pct = round(active_count / len(controls) * 100)

        return {
            "grade": _grade(score),
            "score": score,
            "coverage_pct": coverage_pct,
            "controls": controls,
            "events_24h": {"total": events_24h, "blocked": blocked_24h},
        }
    finally:
        db.close()


def get_governance_kpis(ctx):
    """Governance KPIs — events/blocked today, active devs, blocks MTD.
    Migrated from Executor._tool_get_governance_kpis (epic #1655)."""
    import uuid as _uuid
    from datetime import datetime, timezone
    from sqlalchemy import func as sa_func
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardAuditEvent
    from app.modules.guard.routers.spend import _org_ws_subquery

    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        base_q = db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id.in_(org_ws))
        events_today = base_q.filter(GuardAuditEvent.ts >= today_start).count()
        blocked_today = base_q.filter(
            GuardAuditEvent.ts >= today_start,
            GuardAuditEvent.decision == "blocked",
        ).count()

        active_developers_today = (
            db.query(sa_func.count(sa_func.distinct(GuardAuditEvent.user_email)))
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
        risk_avoided_usd_mtd = round(blocks_mtd * 0.01, 2)

        return {
            "events_today": events_today,
            "blocked_today": blocked_today,
            "active_developers_today": int(active_developers_today),
            "blocks_mtd": blocks_mtd,
            "risk_avoided_usd_mtd": risk_avoided_usd_mtd,
        }
    finally:
        db.close()


def get_framework_coverage(ctx):
    """Installed compliance framework packs with rule counts. Migrated
    from Executor._tool_get_framework_coverage (epic #1655)."""
    from app.core.database import SessionLocal
    from app.modules.guard.models import WorkspaceSkillPack, SkillPack
    from app.modules.guard.routers.spend import _org_ws_subquery

    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, ctx.workspace_id)

        _PACK_TO_FRAMEWORK = {
            "conduct-owasp": "OWASP", "conduct-soc2": "SOC2",
            "conduct-hipaa": "HIPAA", "conduct-pci-dss": "PCI_DSS",
            "conduct-base": "Base", "conduct-iso42001": "ISO_42001",
            "conduct-gdpr": "GDPR", "conduct-nist": "NIST",
            "conduct-nis2": "NIS2", "conduct-dora": "DORA",
        }

        installed_wsps = (
            db.query(WorkspaceSkillPack)
            .filter(WorkspaceSkillPack.workspace_id.in_(org_ws))
            .all()
        )
        seen_slugs: set[str] = set()
        wsp_by_slug: dict[str, WorkspaceSkillPack] = {}
        for wsp in installed_wsps:
            if wsp.pack_slug not in seen_slugs:
                seen_slugs.add(wsp.pack_slug)
                wsp_by_slug[wsp.pack_slug] = wsp

        rules_count_by_slug: dict[str, int] = {}
        if seen_slugs:
            catalog_rows = (
                db.query(SkillPack.slug, SkillPack.rules)
                .filter(SkillPack.slug.in_(list(seen_slugs)))
                .all()
            )
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
        return {"installed_count": len(frameworks), "frameworks": frameworks}
    finally:
        db.close()


def get_governance_narrative(ctx):
    """One-paragraph governance narrative. Migrated from
    Executor._tool_get_governance_narrative (epic #1655)."""
    from app.core.database import SessionLocal
    from app.routers.governance import get_narrative as _get_narrative
    db = SessionLocal()
    try:
        result = _get_narrative(db=db, workspace_id=ctx.workspace_id)
        return {"paragraph": result.paragraph, "source": result.source}
    except Exception as e:
        return {"paragraph": f"Narrative unavailable: {e}", "source": "error"}
    finally:
        db.close()


def get_recent_governance_events(ctx, limit: int = 15, decision: str | None = None,
                                 since: str | None = None, until: str | None = None):
    """Recent Guard audit events for governance dashboards. Migrated from
    Executor._tool_get_recent_governance_events (epic #1655)."""
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardAuditEvent
    from app.modules.guard.routers.spend import _org_ws_subquery

    if decision:
        decision = {"block": "blocked", "warn": "warned", "audit": "audited",
                    "allow": "allowed"}.get(decision, decision)
    if since and until and limit == 15:
        limit = 500

    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        q = db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id.in_(org_ws))
        if decision: q = q.filter(GuardAuditEvent.decision == decision)
        if since: q = q.filter(GuardAuditEvent.ts >= since)
        if until: q = q.filter(GuardAuditEvent.ts <= until)
        rows = q.order_by(GuardAuditEvent.ts.desc()).limit(min(limit, 100)).all()
        return [
            {
                "id": str(e.id), "ts": e.ts.isoformat(), "decision": e.decision,
                "rule_id": e.rule_id, "ai_tool": e.ai_tool, "user_email": e.user_email,
            }
            for e in rows
        ]
    finally:
        db.close()


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_compliance_status",
        description="ASI-01..10 compliance scorecard for this workspace (grade, score, per-control status).",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_compliance_status,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_governance_kpis",
        description="Governance KPIs — events today, blocks today, active devs today, blocks MTD, risk avoided MTD.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_governance_kpis,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_framework_coverage",
        description="Installed compliance packs and rules count per framework (OWASP, SOC2, HIPAA, etc.).",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_framework_coverage,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_governance_narrative",
        description="LLM-generated governance narrative for the workspace. Calls the configured LLM provider.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_governance_narrative,
        annotations=_READ_ONLY_OPEN_WORLD,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_recent_governance_events",
        description="Recent governance-relevant audit events (blocked, warned, audited by default).",
        input_schema={
            "type": "object",
            "properties": {
                "limit": _LIMIT, "decision": _DECISION,
                "since": _TS_SINCE, "until": _TS_UNTIL,
            },
            "required": [],
        },
        impl=get_recent_governance_events,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_governance_summary",
        description="Full framework coverage matrix — installed frameworks, bonus (cross-tag) coverage, and rules totals.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_governance_summary,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_soc2_status",
        description="Rollup for one compliance framework (defaults to SOC2). Returns installed status + rules + controls + recommended pack.",
        input_schema={
            "type": "object",
            "properties": {
                "framework": {
                    "type": "string",
                    "description": "Framework name: SOC2, HIPAA, OWASP, PCI_DSS, ISO_42001, GDPR, EU_AI_ACT, NIST, NIS2, DORA.",
                },
            },
            "required": [],
        },
        impl=get_soc2_status,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_ai_rollout_status",
        description="AI rollout instructions published for the workspace — published flag, content length, version, last update.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_ai_rollout_status,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
