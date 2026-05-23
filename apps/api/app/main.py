from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.routers import credentials, dashboard, environments, projects, runs, webhooks, workflows
from app.routers.runs import workspace_runs_router

app = FastAPI(title="Marshal API", version="0.1.0")

_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return CORS headers even on 500 so the browser sees the error body."""
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={"Access-Control-Allow-Origin": origin},
    )

app.include_router(projects.router)
app.include_router(dashboard.router)
app.include_router(workflows.router)
app.include_router(runs.router)
app.include_router(workspace_runs_router)
app.include_router(credentials.router)
app.include_router(environments.router)
app.include_router(webhooks.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/sandbox")
def sandbox_health():
    """Diagnose which execution backend is active."""
    from app.runtime.sandbox import _modal_available
    from app.core.config import settings
    modal_configured = bool(settings.modal_token_id and settings.modal_token_secret)
    modal_result = None
    if modal_configured:
        try:
            from app.runtime.sandbox import _modal_dispatch
            modal_result = _modal_dispatch("run_shell", {"command": "echo modal-ok"})
            modal_ok = "modal-ok" in modal_result
        except Exception as e:
            modal_result = str(e)
            modal_ok = False
    else:
        modal_ok = False
    return {
        "modal_configured": modal_configured,
        "modal_working":    modal_ok,
        "modal_test_output": modal_result,
        "active_backend":   "modal" if modal_ok else "local",
    }
