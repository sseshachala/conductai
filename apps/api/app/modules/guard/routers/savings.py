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
    booster_saved_tokens: int
    booster_savings_pct: float
    booster_total_reads: int
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

    Accepts a member token, Clerk JWT, or cond_live_ API key (same trust
    model as POST /guard/events). A new row is inserted on every call —
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


@router.get("/summary", response_model=SavingsSummaryOut)
def get_savings_summary(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Return team-wide savings summary — latest row per member, never 404."""
    try:
        return _build_summary(db, workspace_id)
    except Exception as exc:
        log.error("guard.savings_summary_error", workspace_id=workspace_id, exc=str(exc), exc_info=True)
        return _EMPTY_SUMMARY


def _build_summary(db: Session, workspace_id: str) -> SavingsSummaryOut:
    # Latest row per member_email using a subquery
    latest_rows = db.execute(
        text("""
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
                GROUP BY member_email
            ) latest
                ON gs.member_email = latest.member_email
               AND gs.recorded_at  = latest.max_recorded_at
            WHERE gs.workspace_id = :ws
            ORDER BY gs.member_email ASC
        """),
        {"ws": workspace_id},
    ).fetchall()

    if not latest_rows:
        return _EMPTY_SUMMARY

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
            booster_saved_tokens=booster_tokens,
            booster_savings_pct=float(r.booster_savings_pct or 0.0),
            booster_total_reads=int(r.booster_total_reads or 0),
            period_end=r.period_end.isoformat() if r.period_end else "",
            recorded_at=r.recorded_at.isoformat() if r.recorded_at else "",
        ))

    def _tokens_to_usd(tokens: int) -> float:
        return round(tokens * _USD_PER_MILLION_TOKENS / 1_000_000, 6)

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
