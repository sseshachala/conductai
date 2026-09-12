"""Harness-only entry point. Never imported by the production application."""
import os

import uvicorn

if not os.environ.get('CLERK_SECRET_KEY', '').startswith('sk_test_'):
    raise SystemExit('A separate Clerk test instance is required; production keys are refused')
if not os.environ.get('CLERK_FRONTEND_API', '').endswith('.accounts.dev'):
    raise SystemExit('A Clerk development frontend domain is required')

if len(os.environ.get('ENCRYPTION_KEY', '').encode()) < 32:
    raise SystemExit('A persistent local ENCRYPTION_KEY of at least 32 bytes is required')
from app.main import app
from app.modules.guard.trial_challenges import client_ip_from
from fastapi import Request


@app.get('/__e2e/peer', include_in_schema=False)
def peer(request: Request):
    return {'peer': request.client.host, 'effective': client_ip_from(request)}


@app.get('/__e2e/database', include_in_schema=False)
def database_mode():
    from app.core.database import engine
    from sqlalchemy import text
    with engine.connect() as db:
        return dict(db.execute(text("""
            SELECT current_user AS role, rolsuper AS superuser,
                   rolbypassrls AS bypassrls,
                   row_security_active('public.audit_log') AS audit_rls_active
            FROM pg_roles WHERE rolname = current_user
        """)).mappings().one())


# Keep the socket peer intact for the application's explicit CIDR check.
uvicorn.run(app, host='0.0.0.0', port=8000, proxy_headers=False)
