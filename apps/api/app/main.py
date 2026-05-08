from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import credentials, projects, runs, webhooks, workflows

app = FastAPI(title="Marshal API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(workflows.router)
app.include_router(runs.router)
app.include_router(credentials.router)
app.include_router(webhooks.router)


@app.get("/health")
def health():
    return {"status": "ok"}
