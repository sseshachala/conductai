"""Local-only trial email capture; never import from the production app."""
import html
import os

import uvicorn
from fastapi.responses import HTMLResponse

if not os.environ.get("CLERK_SECRET_KEY", "").startswith("sk_test_"):
    raise SystemExit("A Clerk test instance is required")
if "@postgres/conduct_e2e" not in os.environ.get("DATABASE_URL", ""):
    raise SystemExit("The isolated local E2E database is required")
if os.environ.get("APP_URL") != "http://localhost:3107":
    raise SystemExit("Local verification links must use port 3107")

from app.main import app
from app.modules.guard.routers import trial

messages = []


def capture_email(*, slug, to, context, **kwargs):
    if slug != "trial_verify":
        raise ValueError("Only trial verification email is supported")
    messages.append({"to": to, "verify_url": context["verify_url"]})
    return True


trial.send_template_email = capture_email


@app.get("/__trial/inbox", response_class=HTMLResponse)
def inbox():
    rows = "".join(
        f'<li>{html.escape(message["to"])}: '
        f'<a href="{html.escape(message["verify_url"], quote=True)}">Verify local trial</a></li>'
        for message in reversed(messages)
    )
    return HTMLResponse(
        '<!doctype html><meta name="referrer" content="no-referrer">'
        '<title>Local trial inbox</title><h1>Local trial inbox</h1>'
        '<p>Captured locally. No verification email was sent.</p>'
        f'<ul>{rows or "<li>No messages yet.</li>"}</ul>',
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
