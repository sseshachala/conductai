from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
from app.core.config import settings
from app.core.logging import setup_logging
from app.middleware.logging import LoggingMiddleware
from app.routers import credentials, dashboard, email_templates, environments, projects, runs, webhooks, workflows
from app.routers.organizations import router as organizations_router
from app.routers.workspace_projects import router as workspace_projects_router, audit_router as audit_log_router
from app.routers.runs import workspace_runs_router

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
app.include_router(projects.router)
app.include_router(dashboard.router)
app.include_router(workflows.router)
app.include_router(runs.router)
app.include_router(workspace_runs_router)
app.include_router(credentials.router)
app.include_router(environments.router)
app.include_router(email_templates.router)
app.include_router(webhooks.router)


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
