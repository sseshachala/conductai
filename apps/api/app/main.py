from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.routers import credentials, projects, runs, webhooks, workflows

app = FastAPI(title="Marshal API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
app.include_router(workflows.router)
app.include_router(runs.router)
app.include_router(credentials.router)
app.include_router(webhooks.router)


@app.get("/health")
def health():
    return {"status": "ok"}
