from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import credentials, runs, webhooks, workflows

app = FastAPI(title="Marshal API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workflows.router)
app.include_router(runs.router)
app.include_router(credentials.router)
app.include_router(webhooks.router)


@app.get("/health")
def health():
    return {"status": "ok"}
