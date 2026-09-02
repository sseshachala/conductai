"""
POST /guard/savings          — developer pushes RTK + Agent Booster token savings snapshot
GET  /guard/savings/summary  — dashboard reads team-wide savings summary
"""
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.auth import get_guard_hook_auth, get_workspace_id
from app.core.database import get_db
from app.modules.guard.models import GuardSavings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/savings", tags=["guard"])

_USD_PER_MILLION_INPUT_TOKENS  = 3.00   # Claude Sonnet 4.6 input
_USD_PER_MILLION_OUTPUT_TOKENS = 15.00  # Claude Sonnet 4.6 output
# RTK/Booster save primarily input tokens; use a blended 80/20 input/output estimate
_USD_PER_MILLION_TOKENS = _USD_PER_MILLION_INPUT_TOKENS * 0.8 + _USD_PER_MILLION_OUTPUT_TOKENS * 0.2


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class SavingsReport(BaseModel):
    workspace_id: str
    member_email: str
    rtk: dict = {}       # {saved_tokens, savings_pct, total_commands} — empty if rtk not installed
    booster: dict = {}   # {saved_tokens, savings_pct, total_reads} — empty if booster not installed
    period_start: str | None = None
    period_end: str


class SavingsRecordedOut(BaseModel):
    status: str
    recorded_at: str


class MemberSavings(BaseModel):
    member_email: str
    rtk_saved_tokens: int
    rtk_savings_pct: float
    rtk_total_commands: int
    rtk_saved_usd: float
    booster_saved_tokens: int
    booster_savings_pct: float
    booster_total_reads: int
    booster_saved_usd: float
    period_end: str
    recorded_at: str


class TeamTotals(BaseModel):
    rtk_saved_tokens: int
    rtk_saved_usd: float
    booster_saved_tokens: int
    booster_saved_usd: float


class SavingsSummaryOut(BaseModel):
    team_total: TeamTotals
    by_member: list[MemberSavings]
    tools_installed: list[str]


# ── POST /guard/savings ───────────────────────────────────────────────────────

@router.post("", response_model=SavingsRecordedOut, status_code=201)
def record_savings(
    body: SavingsReport,
    db: Session = Depends(get_db),
    _auth_workspace_id: str = Depends(get_guard_hook_auth),
):
    """Developer pushes RTK + Agent Booster token savings snapshot.

    Accepts a member token or Clerk JWT (same trust model as POST /guard/events).
    A new row is inserted on every call —
    history is preserved, no upsert.
    """
    now = _now()

    def _parse_dt(val: str | None) -> datetime | None:
        if not val:
            return None
        try:
            dt = datetime.fromisoformat(val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    period_end = _parse_dt(body.period_end)
    if period_end is None:
        period_end = now

    period_start = _parse_dt(body.period_start)

    rtk = body.rtk or {}
    booster = body.booster or {}

    row = GuardSavings(
        workspace_id=body.workspace_id,
        member_email=body.member_email,
        rtk_saved_tokens=int(rtk.get("saved_tokens", 0)),
        rtk_savings_pct=float(rtk.get("savings_pct", 0.0)),
        rtk_total_commands=int(rtk.get("total_commands", 0)),
        booster_saved_tokens=int(booster.get("saved_tokens", 0)),
        booster_savings_pct=float(booster.get("savings_pct", 0.0)),
        booster_total_reads=int(booster.get("total_reads", 0)),
        period_start=period_start,
        period_end=period_end,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    log.info(
        "guard.savings_recorded",
        workspace_id=body.workspace_id,
        member_email=body.member_email,
        rtk_saved_tokens=row.rtk_saved_tokens,
        booster_saved_tokens=row.booster_saved_tokens,
    )

    # ── Drift detection ───────────────────────────────────────────────────────
    try:
        import uuid as _uuid
        from app.modules.guard.models import GuardConfig
        from app.modules.guard.routers.token_guardrails import _check_guardrail_drift
        from app.modules.guard.routers.notifications import resolve_channels
        from app.modules.guard.routers.events import _fanout_slack

        team = db.query(GuardConfig).filter(
            GuardConfig.workspace_id == _uuid.UUID(body.workspace_id)
        ).first()
        if team is not None:
            current_tools: list[str] = []
            if row.rtk_saved_tokens > 0 or row.rtk_total_commands > 0:
                current_tools.append("rtk")
            if row.booster_saved_tokens > 0 or row.booster_total_reads > 0:
                current_tools.append("booster")

            prev_snap = team.guardrail_snapshot or {}
            current_snapshot = {
                "tools_installed": current_tools,
                "deterministic_offload": prev_snap.get("deterministic_offload", False),
                "metrics_budgets": prev_snap.get("metrics_budgets", False),
            }

            drifts = _check_guardrail_drift(team, current_tools, current_snapshot)
            if drifts:
                text = (
                    f"*ConductGuard drift detected* in workspace *{body.workspace_id}*:\n"
                    + "\n".join(drifts)
                )
                # Route via the per-action fanout — customers configure
                # the drift channel in /theguard/settings > Notifications.
                # Silent when no channels are set (opt-in model).
                channels = resolve_channels(db, body.workspace_id, "drift")
                if channels:
                    _fanout_slack(db, body.workspace_id, channels, text)

            team.guardrail_snapshot = {
                **prev_snap,
                "tools_installed": current_tools,
            }
            db.commit()
    except Exception as exc:
        log.warning("guard.drift_check_failed", exc=str(exc))

    return SavingsRecordedOut(status="ok", recorded_at=row.recorded_at.isoformat())


# ── GET /guard/savings/summary ────────────────────────────────────────────────

_EMPTY_SUMMARY = SavingsSummaryOut(
    team_total=TeamTotals(
        rtk_saved_tokens=0,
        rtk_saved_usd=0.0,
        booster_saved_tokens=0,
        booster_saved_usd=0.0,
    ),
    by_member=[],
    tools_installed=[],
)


class TeamSummaryOut(BaseModel):
    workspace_id: str
    developer_count: int
    total_tokens_saved: int
    total_cost_saved_usd: float
    per_day_usd: float
    per_month_usd: float
    per_year_usd: float
    # Observation window. per_day_usd = total_cost_saved_usd / max(1, days_observed).
    # Consumers should render "$X/day over N days" so the projection has honest scope.
    days_observed: int
    first_recorded_at: str | None
    tools_installed: list[str]


@router.get("/team-summary", response_model=TeamSummaryOut)
def get_team_summary(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Org-level savings aggregate for conduct guard savings --team.

    per_day_usd is the actual daily rate: cumulative USD saved divided by
    the number of days between the earliest reported snapshot and now
    (min 1 day, to avoid div-by-zero on the first sync). per_month and
    per_year are honest projections of that rate.
    """
    summary = _build_summary(db, workspace_id)
    t = summary.team_total
    total_usd = round(t.rtk_saved_usd + t.booster_saved_usd, 6)

    # Earliest snapshot across all members in this workspace's org scope.
    first_ts_row = db.execute(
        text("""
            SELECT MIN(recorded_at) AS first_ts
            FROM guard_savings
            WHERE workspace_id = :ws
        """),
        {"ws": workspace_id},
    ).fetchone()
    first_ts = first_ts_row.first_ts if first_ts_row else None

    if first_ts is not None:
        if first_ts.tzinfo is None:
            first_ts = first_ts.replace(tzinfo=timezone.utc)
        days_observed = max(1, (_now() - first_ts).days)
    else:
        days_observed = 1

    per_day = round(total_usd / days_observed, 2)
    return TeamSummaryOut(
        workspace_id=workspace_id,
        developer_count=len(summary.by_member),
        total_tokens_saved=t.rtk_saved_tokens + t.booster_saved_tokens,
        total_cost_saved_usd=total_usd,
        per_day_usd=per_day,
        per_month_usd=round(per_day * 30, 2),
        per_year_usd=round(per_day * 365, 2),
        days_observed=days_observed,
        first_recorded_at=first_ts.isoformat() if first_ts is not None else None,
        tools_installed=summary.tools_installed,
    )


@router.get("/summary", response_model=SavingsSummaryOut)
def get_savings_summary(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    month: str | None = Query(default=None, description="YYYY-MM. Cumulative as of end of month; None = all time."),
):
    """Return team-wide savings summary — latest row per member, never 404.

    When month is passed, returns cumulative-as-of-end-of-month totals
    (latest guard_savings row per member with recorded_at < first day of
    next month). Snapshots are cumulative, so this is the running total the
    team had at that point in time.
    """
    try:
        return _build_summary(db, workspace_id, month)
    except Exception as exc:
        log.error("guard.savings_summary_error", workspace_id=workspace_id, exc=str(exc), exc_info=True)
        return _EMPTY_SUMMARY


def _month_end(month: str | None) -> datetime | None:
    """First instant of the month after `month` (YYYY-MM). None passes through."""
    if not month:
        return None
    try:
        start = datetime.strptime(month, "%Y-%m").replace(
            tzinfo=timezone.utc, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    except ValueError:
        return None
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)


def _build_summary(db: Session, workspace_id: str, month: str | None = None) -> SavingsSummaryOut:
    # Latest row per member_email as of end of month (or all time when month is None).
    cutoff = _month_end(month)
    params: dict = {"ws": workspace_id}
    cutoff_clause = ""
    if cutoff is not None:
        params["cutoff"] = cutoff
        cutoff_clause = "AND recorded_at < :cutoff"
    latest_rows = db.execute(
        text(f"""
            SELECT
                gs.member_email,
                gs.rtk_saved_tokens,
                gs.rtk_savings_pct,
                gs.rtk_total_commands,
                gs.booster_saved_tokens,
                gs.booster_savings_pct,
                gs.booster_total_reads,
                gs.period_end,
                gs.recorded_at
            FROM guard_savings gs
            INNER JOIN (
                SELECT member_email, MAX(recorded_at) AS max_recorded_at
                FROM guard_savings
                WHERE workspace_id = :ws
                  {cutoff_clause}
                GROUP BY member_email
            ) latest
                ON gs.member_email = latest.member_email
               AND gs.recorded_at  = latest.max_recorded_at
            WHERE gs.workspace_id = :ws
              {cutoff_clause}
            ORDER BY gs.member_email ASC
        """),
        params,
    ).fetchall()

    if not latest_rows:
        return _EMPTY_SUMMARY

    def _tokens_to_usd(tokens: int) -> float:
        return round(tokens * _USD_PER_MILLION_TOKENS / 1_000_000, 6)

    by_member: list[MemberSavings] = []
    total_rtk_tokens = 0
    total_booster_tokens = 0
    has_rtk = False
    has_booster = False

    for r in latest_rows:
        rtk_tokens = int(r.rtk_saved_tokens or 0)
        booster_tokens = int(r.booster_saved_tokens or 0)
        total_rtk_tokens += rtk_tokens
        total_booster_tokens += booster_tokens

        if rtk_tokens > 0 or int(r.rtk_total_commands or 0) > 0:
            has_rtk = True
        if booster_tokens > 0 or int(r.booster_total_reads or 0) > 0:
            has_booster = True

        by_member.append(MemberSavings(
            member_email=r.member_email,
            rtk_saved_tokens=rtk_tokens,
            rtk_savings_pct=float(r.rtk_savings_pct or 0.0),
            rtk_total_commands=int(r.rtk_total_commands or 0),
            rtk_saved_usd=_tokens_to_usd(rtk_tokens),
            booster_saved_tokens=booster_tokens,
            booster_savings_pct=float(r.booster_savings_pct or 0.0),
            booster_total_reads=int(r.booster_total_reads or 0),
            booster_saved_usd=_tokens_to_usd(booster_tokens),
            period_end=r.period_end.isoformat() if r.period_end else "",
            recorded_at=r.recorded_at.isoformat() if r.recorded_at else "",
        ))

    tools_installed: list[str] = []
    if has_rtk:
        tools_installed.append("rtk")
    if has_booster:
        tools_installed.append("booster")

    return SavingsSummaryOut(
        team_total=TeamTotals(
            rtk_saved_tokens=total_rtk_tokens,
            rtk_saved_usd=_tokens_to_usd(total_rtk_tokens),
            booster_saved_tokens=total_booster_tokens,
            booster_saved_usd=_tokens_to_usd(total_booster_tokens),
        ),
        by_member=by_member,
        tools_installed=tools_installed,
    )
