from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
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
from app.modules.guard.routers import mcp as guard_mcp
from app.modules.guard.routers import proxy as guard_proxy
from app.modules.guard.routers import ws as guard_ws
from app.modules.guard.routers import signing_key as guard_signing_key
from app.modules.guard.routers import sessions as guard_sessions
from app.modules.guard.routers import discovery as guard_discovery
from app.modules.guard.routers import memory_search as guard_memory_search
from app.modules.guard.routers import verify as guard_verify
from app.modules.guard.routers import knowledge_search as guard_knowledge_search
from app.modules.glens.routers import chat as glens_chat
from app.modules.telemetry import routes as telemetry_routes
from app.routers.organizations import router as organizations_router
from app.routers.workspaces import router as workspaces_router
from app.routers.workspace_projects import router as workspace_projects_router, audit_router as audit_log_router, preferences_router as workspace_preferences_router, notifications_router
from app.routers.runs import workspace_runs_router
from app.routers.rbac import router as rbac_router, me_router as me_rbac_router
from app.routers.mcp import router as mcp_router
from app.routers.mcp_servers import router as mcp_servers_router
from app.routers.generate import router as generate_router
from app.routers.compliance import router as compliance_router
from app.routers.cedar_import import router as cedar_import_router
from app.routers.okta_sync import router as okta_sync_router
from app.routers.governance import router as governance_router
from app.routers.sdd import router as sdd_router
from app.routers.session_reports import router as session_reports_router
from app.routers.team_memory import router as team_memory_router
from app.routers.meta import router as meta_router
from app.routers.share import router as share_router
from app.modules.agent_identity.router import router as agent_identity_router
from app.routers.security import router as security_findings_router
from app.modules.auth.cli_token import router as cli_auth_router
from app.modules.auth.token_exchange import router as token_exchange_router
from app.routers.team_os import router as team_os_router

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

_STATIC = Path(__file__).parent / "static"

@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.png", include_in_schema=False)
async def favicon():
    return FileResponse(_STATIC / "favicon.png", media_type="image/png")

_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
if not _origins:
    log.warning("cors.no_origins_configured", msg="ALLOWED_ORIGINS is empty — all cross-origin requests blocked. Set ALLOWED_ORIGINS in .env to enable CORS.")

app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,  # empty list = block all cross-origin requests
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
app.include_router(workspaces_router)
app.include_router(workspace_projects_router)
app.include_router(audit_log_router)
app.include_router(workspace_preferences_router)
app.include_router(notifications_router)
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
app.include_router(guard_mcp.router)
app.include_router(guard_mcp.well_known_router)
app.include_router(guard_proxy.router)
app.include_router(guard_proxy.guard_router)
app.include_router(guard_ws.router)
app.include_router(guard_signing_key.router)
app.include_router(guard_sessions.router)
app.include_router(guard_discovery.router)
app.include_router(guard_verify.router)
app.include_router(guard_knowledge_search.router)
app.include_router(glens_chat.router)
app.include_router(telemetry_routes.router)
app.include_router(rbac_router)
app.include_router(me_rbac_router)
app.include_router(mcp_router)
app.include_router(mcp_servers_router)
app.include_router(generate_router)
app.include_router(compliance_router)
app.include_router(cedar_import_router)
app.include_router(okta_sync_router)
app.include_router(governance_router)
app.include_router(sdd_router)
app.include_router(session_reports_router)
app.include_router(team_memory_router)
app.include_router(meta_router)
app.include_router(share_router)
app.include_router(agent_identity_router)
app.include_router(cli_auth_router)
app.include_router(token_exchange_router)
app.include_router(security_findings_router)
app.include_router(team_os_router)


@app.on_event("startup")
def _startup() -> None:
    import threading
    from app.routers.eval import _cached_report

    def _warm() -> None:
        try:
            _cached_report()
            log.info("eval.cache_warmed")
        except Exception as exc:
            log.warning("eval.cache_warm_failed", error=str(exc))

    def _seed() -> None:
        try:
            from scripts.seed_skill_packs import run as seed_skill_packs
            seed_skill_packs(dry_run=False)
            log.info("guard.skill_packs_seeded")
        except Exception as exc:
            log.error("guard.skill_packs_seed_failed", error=str(exc), exc_info=exc)

    threading.Thread(target=_warm, daemon=True, name="eval-cache-warmer").start()
    threading.Thread(target=_seed, daemon=True, name="skill-pack-seeder").start()


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
