"""Governance dashboard endpoints — aggregate compliance + run + spend data
into the three-view outcome surface defined by issue #750.

Phase 1 endpoints:
    GET /governance/frameworks   — multi-framework coverage matrix
    GET /governance/narrative    — plain-English summary paragraph (template-based for now)
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import require_permission, get_workspace_id
from app.core.database import get_db
from app.modules.guard.models import (
    GuardAuditEvent,
    SkillPack,
    WorkspaceSkillPack,
)


router = APIRouter(prefix="/governance", tags=["governance"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class FrameworkRow(BaseModel):
    framework: str               # e.g. "SOC2"
    rules_count: int             # how many installed rules carry this framework tag
    controls: list[str]          # distinct control IDs covered (e.g. ["CC6.1", "CC8.1"])
    packs: list[str]             # pack slugs that contribute (e.g. ["conduct-base", "conduct-soc2"])


class BonusFrameworkRow(BaseModel):
    framework: str
    rules_count: int
    controls: list[str]
    packs: list[str]                # packs that cross-tag this framework
    recommended_pack: str | None    # slug of the dedicated pack, if one exists


class FrameworksOut(BaseModel):
    installed: list[FrameworkRow]   # frameworks where a dedicated pack is installed
    bonus: list[BonusFrameworkRow]  # frameworks getting cross-coverage only
    total_rules: int                # sum of all installed rules (across packs)
    rules_with_framework: int       # how many of those have at least one framework tag


# Maps pack slug → the framework it's designed for. None = general (no primary).
# Used to split framework coverage into "installed" (dedicated pack present) and
# "bonus" (cross-tagged rules from packs designed for other frameworks).
PACK_PRIMARY_FRAMEWORK: dict[str, str | None] = {
    "conduct-soc2":     "SOC2",
    "conduct-owasp":    "OWASP",
    "conduct-hipaa":    "HIPAA",
    "conduct-pci-dss":  "PCI_DSS",
    "conduct-base":     None,
}

# Reverse map: given a framework name, recommend the dedicated pack to install.
# None = no dedicated pack ships today (e.g. GDPR, EU_AI_Act, ISO_42001).
RECOMMENDED_PACK: dict[str, str | None] = {
    "SOC2":      "conduct-soc2",
    "OWASP":     "conduct-owasp",
    "HIPAA":     "conduct-hipaa",
    "PCI_DSS":   "conduct-pci-dss",
    "ISO_42001": None,
    "GDPR":      None,
    "EU_AI_ACT": None,
    "NIST":      None,
    "NIS2":      None,
    "DORA":      None,
}


class NarrativeOut(BaseModel):
    paragraph: str
    generated_at: datetime
    source: str                  # "template" | "llm"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _latest_pack(db: Session, slug: str, pinned: str | None) -> SkillPack | None:
    if pinned:
        return db.get(SkillPack, (slug, pinned))
    return (
        db.query(SkillPack)
        .filter(SkillPack.slug == slug)
        .order_by(SkillPack.version.desc())
        .first()
    )


def _split_framework(token: str) -> tuple[str, str | None]:
    """Parse 'SOC2:CC6.1' → ('SOC2', 'CC6.1'). Bare 'OWASP_TOP_10' → ('OWASP_TOP_10', None)."""
    if ":" in token:
        fw, ctrl = token.split(":", 1)
        return fw.strip(), ctrl.strip()
    return token.strip(), None


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _compute_framework_coverage(db: Session, workspace_id: str) -> FrameworksOut:
    """Shared logic — called by the public endpoint and by /narrative."""
    ws_uuid = uuid.UUID(workspace_id)

    installed = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id == ws_uuid)
        .all()
    )

    # framework → {controls: set, packs: set, rules: int}
    agg: dict[str, dict] = defaultdict(lambda: {"controls": set(), "packs": set(), "rules": 0})
    total_rules = 0
    rules_with_framework = 0

    for wp in installed:
        pack = _latest_pack(db, wp.pack_slug, wp.pinned_version)
        if not pack:
            continue
        for rule in pack.rules or []:
            total_rules += 1
            fw_tokens = rule.get("frameworks") or []
            if not fw_tokens:
                continue
            rules_with_framework += 1
            for tok in fw_tokens:
                fw, ctrl = _split_framework(tok)
                bucket = agg[fw]
                bucket["rules"] += 1
                if ctrl:
                    bucket["controls"].add(ctrl)
                bucket["packs"].add(pack.slug)

    # Set of frameworks for which a dedicated pack is installed.
    installed_frameworks = {
        PACK_PRIMARY_FRAMEWORK.get(wp.pack_slug)
        for wp in installed
        if PACK_PRIMARY_FRAMEWORK.get(wp.pack_slug) is not None
    }

    installed_rows: list[FrameworkRow] = []
    bonus_rows: list[BonusFrameworkRow] = []
    for fw, data in sorted(agg.items(), key=lambda kv: -kv[1]["rules"]):
        if fw in installed_frameworks:
            installed_rows.append(FrameworkRow(
                framework=fw,
                rules_count=data["rules"],
                controls=sorted(data["controls"]),
                packs=sorted(data["packs"]),
            ))
        else:
            bonus_rows.append(BonusFrameworkRow(
                framework=fw,
                rules_count=data["rules"],
                controls=sorted(data["controls"]),
                packs=sorted(data["packs"]),
                recommended_pack=RECOMMENDED_PACK.get(fw),
            ))

    return FrameworksOut(
        installed=installed_rows,
        bonus=bonus_rows,
        total_rules=total_rules,
        rules_with_framework=rules_with_framework,
    )


@router.get("/frameworks", response_model=FrameworksOut)
def get_framework_coverage(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.view")),
):
    """Aggregate all installed-pack rules by framework tag."""
    return _compute_framework_coverage(db, workspace_id)


@router.get("/narrative", response_model=NarrativeOut)
def get_narrative(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_own")),
):
    """Plain-English summary. Template-based; LLM upgrade in Phase 2."""
    ws_uuid = uuid.UUID(workspace_id)
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    installed_packs = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id == ws_uuid)
        .count()
    )

    blocked_7d = (
        db.query(GuardAuditEvent)
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.decision == "blocked",
            GuardAuditEvent.ts >= week_ago,
        )
        .count()
    )

    warned_7d = (
        db.query(GuardAuditEvent)
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.decision == "warned",
            GuardAuditEvent.ts >= week_ago,
        )
        .count()
    )

    total_7d = (
        db.query(GuardAuditEvent)
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= week_ago,
        )
        .count()
    )

    # Frameworks covered — count primary (installed dedicated pack) first; mention bonus only if no primary.
    fw_resp = _compute_framework_coverage(db, workspace_id)
    primary_count = len(fw_resp.installed)
    bonus_count = len(fw_resp.bonus)
    fw_count = primary_count
    fw_names = ", ".join(r.framework for r in fw_resp.installed[:3])

    if total_7d == 0 and installed_packs == 0:
        para = (
            "No AI activity recorded yet. Install a compliance pack from the marketplace "
            "to start covering frameworks like SOC 2, ISO 42001, OWASP, or HIPAA."
        )
    else:
        bits = []
        if total_7d > 0:
            bits.append(f"Guard screened {total_7d:,} AI tool calls this week")
        if blocked_7d > 0:
            bits.append(f"intercepted {blocked_7d} risky actions")
        if warned_7d > 0:
            bits.append(f"flagged {warned_7d} for review")
        if fw_count > 0:
            bits.append(f"covering {fw_count} frameworks ({fw_names})")
            if bonus_count > 0:
                bits.append(f"with bonus coverage on {bonus_count} more")
        elif bonus_count > 0:
            bits.append(f"with bonus coverage on {bonus_count} frameworks from {installed_packs} pack(s)")
        elif installed_packs > 0:
            bits.append(f"with {installed_packs} pack(s) installed")
        para = ". ".join(b.capitalize() if i == 0 else b for i, b in enumerate(bits)) + "."

    return NarrativeOut(paragraph=para, generated_at=now, source="template")


# ── Drill-down + events feed (governance polish A) ──────────────────────────

class RuleDrillRow(BaseModel):
    rule_id: str
    description: str | None = None
    action: str
    severity: str | None = None
    pack_slug: str
    match_tool: str | None = None
    match_pattern: str | None = None
    match_path_pattern: str | None = None
    recommendation: str | None = None
    iso_control: str | None = None
    frameworks: list[str] = []
    events_30d: int = 0


class ControlDrillOut(BaseModel):
    framework: str
    control: str | None              # may be None when drilling by framework only
    rules: list[RuleDrillRow]


class RecentEventOut(BaseModel):
    id: str
    ts: datetime
    decision: str                    # blocked | warned | allowed | audited
    rule_id: str | None = None
    ai_tool: str
    tool_call: str
    user_email: str | None = None
    input_summary: str | None = None
    conductai_run_id: str | None = None
    blast_radius: dict | None = None


@router.get("/frameworks/{framework}/controls/{control}/rules", response_model=ControlDrillOut)
def get_rules_for_control(
    framework: str,
    control: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.view")),
):
    """Return all rules covering a specific control in a framework, plus how
    many times each rule has fired in the last 30 days."""
    ws_uuid = uuid.UUID(workspace_id)
    target_token_prefix = f"{framework}:{control}"
    target_token_bare = framework  # rules may tag bare framework w/o control

    installed = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id == ws_uuid)
        .all()
    )

    matched: dict[str, RuleDrillRow] = {}
    for wp in installed:
        pack = _latest_pack(db, wp.pack_slug, wp.pinned_version)
        if not pack:
            continue
        for rule in pack.rules or []:
            fw_tokens = rule.get("frameworks") or []
            if not any(t == target_token_prefix or t == target_token_bare for t in fw_tokens):
                continue
            rid = rule.get("id") or rule.get("rule_id") or ""
            if rid and rid not in matched:
                matched[rid] = RuleDrillRow(
                    rule_id=rid,
                    description=rule.get("description"),
                    action=rule.get("action", "block"),
                    severity=rule.get("severity"),
                    pack_slug=pack.slug,
                    match_tool=rule.get("match_tool"),
                    match_pattern=rule.get("match_pattern"),
                    match_path_pattern=rule.get("match_path_pattern"),
                    recommendation=rule.get("recommendation"),
                    iso_control=rule.get("iso_control"),
                    frameworks=fw_tokens,
                    events_30d=0,
                )

    if matched:
        since = datetime.now(timezone.utc) - timedelta(days=30)
        rule_ids = list(matched.keys())
        from sqlalchemy import func as _func
        rows = (
            db.query(GuardAuditEvent.rule_id, _func.count(GuardAuditEvent.id))
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.rule_id.in_(rule_ids),
                GuardAuditEvent.ts >= since,
            )
            .group_by(GuardAuditEvent.rule_id)
            .all()
        )
        for rid, cnt in rows:
            if rid in matched:
                matched[rid].events_30d = int(cnt)

    return ControlDrillOut(
        framework=framework,
        control=control,
        rules=sorted(matched.values(), key=lambda r: (-r.events_30d, r.rule_id)),
    )


@router.get("/events/recent", response_model=list[RecentEventOut])
def get_recent_events(
    limit: int = 20,
    decision: str | None = None,    # filter: blocked | warned | allowed | audited
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_own")),
):
    """Recent guard events for the dashboard activity feed. Defaults to last
    20 events; pass ?decision=blocked or ?decision=warned to filter."""
    ws_uuid = uuid.UUID(workspace_id)
    limit = max(1, min(limit, 100))

    q = (
        db.query(GuardAuditEvent)
        .filter(GuardAuditEvent.workspace_id == ws_uuid)
        .order_by(GuardAuditEvent.ts.desc())
    )
    if decision:
        q = q.filter(GuardAuditEvent.decision == decision)

    rows = q.limit(limit).all()
    return [
        RecentEventOut(
            id=str(r.id),
            ts=r.ts,
            decision=r.decision,
            rule_id=r.rule_id,
            ai_tool=r.ai_tool,
            tool_call=r.tool_call,
            user_email=r.user_email,
            input_summary=(r.input_summary or "")[:200] if r.input_summary else None,
            conductai_run_id=r.conductai_run_id,
            blast_radius=r.blast_radius,
        )
        for r in rows
    ]


# ── KPIs with deltas (governance polish #3) ─────────────────────────────────

class KpiValue(BaseModel):
    value: int
    avg_7d: float | None = None       # 7-day daily average (the baseline)
    delta_pct: int | None = None      # signed % delta vs avg_7d; None when baseline is 0


class KpisOut(BaseModel):
    events_today: KpiValue
    blocked_today: KpiValue
    active_developers_today: KpiValue
    risk_avoided_usd_mtd: int       # blocks month-to-date × industry-avg incident cost
    blocks_mtd: int                 # raw count behind the $ figure (for tooltip / explainer)


# Industry-average cost of a single prevented incident, used to translate raw
# block counts into a $ figure on the dashboard. Conservative end of the
# $15K–$50K range commonly cited for mid-market engineering incidents.
# ponytail: hardcoded constant, make per-workspace configurable when finance asks.
_INCIDENT_AVG_USD = 15000


def _kpi(value: int, avg_7d: float) -> KpiValue:
    """Build a KpiValue with delta. Avoids divide-by-zero by returning None
    delta when the baseline is 0."""
    if avg_7d <= 0:
        return KpiValue(value=value, avg_7d=None if avg_7d == 0 else avg_7d, delta_pct=None)
    delta = round((value - avg_7d) / avg_7d * 100)
    return KpiValue(value=value, avg_7d=round(avg_7d, 1), delta_pct=delta)


@router.get("/kpis", response_model=KpisOut)
def get_kpis(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_own")),
):
    """Today's headline metrics with 7-day-average baseline + delta %.
    Used by the governance dashboard cards to show direction (up/down)."""
    ws_uuid = uuid.UUID(workspace_id)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    baseline_start = today_start - timedelta(days=7)

    from sqlalchemy import func as _func, distinct

    # --- Events today
    events_today = (
        db.query(_func.count(GuardAuditEvent.id))
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= today_start,
        )
        .scalar() or 0
    )
    # 7d total (yesterday backwards 7 full days) — divide by 7 for daily avg
    events_7d_total = (
        db.query(_func.count(GuardAuditEvent.id))
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= baseline_start,
            GuardAuditEvent.ts < today_start,
        )
        .scalar() or 0
    )
    events_7d_avg = events_7d_total / 7.0

    # --- Blocked today
    blocked_today = (
        db.query(_func.count(GuardAuditEvent.id))
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.decision == "blocked",
            GuardAuditEvent.ts >= today_start,
        )
        .scalar() or 0
    )
    blocked_7d_total = (
        db.query(_func.count(GuardAuditEvent.id))
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.decision == "blocked",
            GuardAuditEvent.ts >= baseline_start,
            GuardAuditEvent.ts < today_start,
        )
        .scalar() or 0
    )
    blocked_7d_avg = blocked_7d_total / 7.0

    # --- Active developers today (distinct user_email with at least one event)
    active_today = (
        db.query(_func.count(distinct(GuardAuditEvent.user_email)))
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.user_email.isnot(None),
            GuardAuditEvent.ts >= today_start,
        )
        .scalar() or 0
    )
    # For "active devs" baseline, we want avg distinct devs per day in the
    # last 7 days — approximate with the simple count over 7 days / 7. Good
    # enough for a direction signal, not a perfect metric.
    active_7d_total = (
        db.query(_func.count(distinct(GuardAuditEvent.user_email)))
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.user_email.isnot(None),
            GuardAuditEvent.ts >= baseline_start,
            GuardAuditEvent.ts < today_start,
        )
        .scalar() or 0
    )
    # Active devs collapses across days, so dividing by 7 understates. Take the
    # raw count as the baseline for now — direction is what matters.
    active_baseline = float(active_7d_total)

    # --- Risk avoided $ (month-to-date)
    month_start = today_start.replace(day=1)
    blocks_mtd = (
        db.query(_func.count(GuardAuditEvent.id))
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.decision == "blocked",
            GuardAuditEvent.ts >= month_start,
        )
        .scalar() or 0
    )

    return KpisOut(
        events_today=_kpi(events_today, events_7d_avg),
        blocked_today=_kpi(blocked_today, blocked_7d_avg),
        active_developers_today=_kpi(active_today, active_baseline),
        risk_avoided_usd_mtd=blocks_mtd * _INCIDENT_AVG_USD,
        blocks_mtd=blocks_mtd,
    )
