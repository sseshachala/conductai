from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
from app.core.config import settings
from app.core.logging import setup_logging
from app.middleware.logging import LoggingMiddleware
from app.routers import credentials, email_templates, environments, playbooks, projects, runs, webhooks, workflows
from app.routers.playbooks import catalog_router as playbooks_catalog_router
from app.routers.eval import router as eval_router
from app.routers.insights import router as insights_router
from app.modules.guard.routers import config as guard_config
from app.modules.guard.routers import members as guard_members
from app.modules.guard.routers import policies as guard_policies
from app.modules.guard.routers import events as guard_events
from app.modules.guard.routers import spend as guard_spend
from app.modules.guard.routers import savings as guard_savings
from app.modules.guard.routers import developer_tools as guard_developer_tools
from app.modules.guard.routers import token_guardrails as guard_token_guardrails
from app.modules.guard.routers import session_reports as guard_session_reports
from app.routers.organizations import router as organizations_router
from app.routers.workspace_projects import router as workspace_projects_router, audit_router as audit_log_router, preferences_router as workspace_preferences_router, notifications_router
from app.routers.runs import workspace_runs_router
from app.routers.api_keys import router as api_keys_router, me_router
from app.routers.rbac import router as rbac_router, me_router as me_rbac_router
from app.routers.mcp import router as mcp_router
from app.routers.generate import router as generate_router
from app.routers.security import router as security_router
from app.routers.secure import router as secure_router
from app.routers.sdd import router as sdd_router
from app.routers.session_reports import router as session_reports_router
from app.routers.team_memory import router as team_memory_router

setup_logging()
log = structlog.get_logger(__name__)

if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration(), StarletteIntegration()],
        traces_sample_rate=0.1,
        environment=settings.environment,
        release=settings.app_version,
    )

app = FastAPI(title="Marshal API", version="0.1.0")

_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    import uuid
    error_id = str(uuid.uuid4())[:8]
    log.error("unhandled_exception", error_id=error_id, exc_info=exc)
    origin = request.headers.get("origin", "")
    headers = {"Access-Control-Allow-Origin": origin} if origin in _origins else {}
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred.", "error_id": error_id},
        headers=headers,
    )

app.include_router(organizations_router)
app.include_router(workspace_projects_router)
app.include_router(audit_log_router)
app.include_router(workspace_preferences_router)
app.include_router(notifications_router)
app.include_router(api_keys_router)
app.include_router(me_router)
app.include_router(projects.router)
app.include_router(playbooks.router)
app.include_router(playbooks_catalog_router)
app.include_router(workflows.router)
app.include_router(runs.router)
app.include_router(workspace_runs_router)
app.include_router(credentials.router)
app.include_router(environments.router)
app.include_router(email_templates.router)
app.include_router(webhooks.router)
app.include_router(eval_router)
app.include_router(insights_router)
app.include_router(guard_config.router)
app.include_router(guard_config.join_router)
app.include_router(guard_members.router)
app.include_router(guard_policies.router)
app.include_router(guard_events.router)
app.include_router(guard_spend.router)
app.include_router(guard_savings.router)
app.include_router(guard_developer_tools.router)
app.include_router(guard_token_guardrails.router)
app.include_router(guard_session_reports.router)
app.include_router(rbac_router)
app.include_router(me_rbac_router)
app.include_router(mcp_router)
app.include_router(generate_router)
app.include_router(security_router)
app.include_router(secure_router)
app.include_router(sdd_router)
app.include_router(session_reports_router)
app.include_router(team_memory_router)


@app.on_event("startup")
def _warm_eval_cache() -> None:
    """Pre-compute the structural eval report in the background so the first
    real request hits the cache instead of paying the full scoring cost."""
    import threading
    from app.routers.eval import _cached_report

    def _warm() -> None:
        try:
            _cached_report()
            log.info("eval.cache_warmed")
        except Exception as exc:
            log.warning("eval.cache_warm_failed", error=str(exc))

    threading.Thread(target=_warm, daemon=True, name="eval-cache-warmer").start()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/sandbox")
def sandbox_health():
    """Diagnose which execution backend is active.
    Modal is workspace-scoped — platform-level Modal config is intentionally removed (#202).
    """
    return {
        "modal_backend": "workspace-scoped",
        "note": "Modal credentials must be set in Settings → Environments (MODAL_TOKEN_ID / MODAL_TOKEN_SECRET). No platform-level fallback.",
        "active_backend": "modal (subprocess-isolated) or local",
    }
