"""ConductGuard spend — shared schemas, scoping and billing-period helpers."""

import uuid
from datetime import datetime, timezone
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models.workspace import Workspace


def _org_ws_subquery(db: Session, workspace_id: str):
    """Strict single-workspace scoping. See issue #1564."""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return db.query(Workspace.id).filter(Workspace.id == None)  # noqa: E711 — safe empty subquery
    return db.query(Workspace.id).filter(Workspace.id == ws_uuid)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _current_period_start() -> datetime:
    now = _now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _period_label() -> str:
    now = _now()
    return now.strftime("%Y-%m")


def _parse_period_start(month: str | None) -> datetime:
    """Parse 'YYYY-MM' into period start datetime. Falls back to current month."""
    if month:
        try:
            return datetime.strptime(month, "%Y-%m").replace(
                tzinfo=timezone.utc, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        except ValueError:
            pass
    return _current_period_start()


def _next_period_start(period_start: datetime) -> datetime:
    """First instant of the calendar month after period_start."""
    if period_start.month == 12:
        return period_start.replace(year=period_start.year + 1, month=1)
    return period_start.replace(month=period_start.month + 1)


class DeveloperSpend(BaseModel):
    # Name collides with another schema, so FastAPI qualifies the OpenAPI
    # component by module; pin the pre-split module to keep it stable.
    __module__ = "app.modules.guard.routers.spend"

    email: str
    tokens_after: int
    cost_usd: float
    saved_usd: float
    sessions: int
    detected_tools: list[str] = []
    mcp_registered: list[str] = []
    hook_registered: list[str] = []


class ToolSpend(BaseModel):
    ai_tool: str
    tokens_after: int
    cost_usd: float
    tokens_saved: int = 0
    cost_saved: float = 0.0


class ModelSpend(BaseModel):
    # provider is the vendor namespace (anthropic, openai, perplexity, ...);
    # model is the concrete vendor id (gpt-4o, claude-sonnet-4-5, ...). Both
    # are populated only for proxy-routed audit events — hook-only rows are
    # excluded from these aggregates by a `WHERE model IS NOT NULL` filter.
    provider: str
    model: str
    tokens_after: int
    cost_usd: float


class ProviderSpend(BaseModel):
    provider: str
    tokens_after: int
    cost_usd: float


class SpendSummary(BaseModel):
    workspace_id: str
    period: str
    active_developers: int
    events_today: int
    blocked_today: int
    tokens_saved_today: int
    total_tokens_before: int
    total_tokens_after: int
    total_saved_pct: int
    total_cost_usd: float
    total_saved_usd: float
    sessions: int = 0
    hook_sessions: int = 0
    by_developer: list[DeveloperSpend]
    by_ai_tool: list[ToolSpend]
    by_model: list[ModelSpend] = []
    by_provider: list[ProviderSpend] = []


class SessionOut(BaseModel):
    # Name collides with another schema, so FastAPI qualifies the OpenAPI
    # component by module; pin the pre-split module to keep it stable.
    __module__ = "app.modules.guard.routers.spend"

    id: str
    workspace_id: str
    clerk_user_id: str | None
    user_email: str | None
    ai_tool: str
    started_at: str | None
    ended_at: str | None
    total_tokens_before: int
    total_tokens_after: int
    total_cost_usd: float
    total_saved_usd: float
    event_count: int
    violations_count: int
    client_ip: str | None = None
    os_info: str | None = None
    hostname: str | None = None
    intent: str | None = None
    session_parse_status: str | None = None


class BudgetCreate(BaseModel):
    workspace_id: str
    clerk_user_id: str | None = None    # null = workspace-wide
    email: str | None = None            # per-developer: frontend sends email, backend resolves to clerk_user_id
    agent_identity_id: str | None = None  # null = across all agents; non-null = per-agent budget (Added 0140)
    ai_tool: str | None = None          # null = across all tools; non-null = per-tool budget
    hard_cap_enabled: bool | None = None  # per-budget flag; the workspace-default row acts as a master switch, non-default rows opt-in individually
    monthly_limit_usd: float
    alert_threshold_pct: int = 80
    hard_limit_usd: float | None = None
    default_per_developer_usd: float | None = None  # workspace-wide record only


class BudgetOut(BaseModel):
    id: str
    workspace_id: str
    clerk_user_id: str | None
    email: str | None = None
    agent_identity_id: str | None = None  # Added 0140
    ai_tool: str | None = None
    hard_cap_enabled: bool = False
    monthly_limit_usd: float
    alert_threshold_pct: int
    hard_limit_usd: float | None
    default_per_developer_usd: float | None
    current_month_cost_usd: float
    created_at: str
    updated_at: str


class BudgetCheckOut(BaseModel):
    hard_blocked: bool
    reason: str | None = None
    monthly_cost_usd: float
    hard_limit_usd: float | None


class ReservationScopeOut(BaseModel):
    """Per-scope reservation record for the drawer."""
    reservation_id: str
    workspace_id: str
    clerk_user_id: str | None
    agent_identity_id: str | None
    # R13: populated by the BEFORE DELETE trigger on agent_identities
    # (migration 0152). Non-null after the agent is deleted; UI renders
    # "agent:<id> (deleted)" so historical rows do not look orphaned.
    deleted_agent_identity_id: str | None = None
    ai_tool: str | None
    source: str | None
    client_tool: str | None
    period_key: str
    estimated_cents: int
    actual_cents: int | None
    status: str  # 'open' | 'released' | 'committed'
    created_at: str
    resolved_at: str | None
