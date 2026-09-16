"""Local Docker fixture only. Its JSON stdout is private IPC to local_smoke.py."""
import json
import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.engine import make_url

url = make_url(os.environ['DATABASE_URL'])
if url.host != 'postgres' or url.database != 'conduct_mcp_canary':
    raise SystemExit('Refusing non-canary database')

from app.main import app  # register all ORM models
from app.core.crypto import encrypt
from app.core.database import SessionLocal
from app.models.workspace import Workspace
from app.models.workspace_user import WorkspaceUser
from app.models.user import User
from app.modules.agent_identity.models import AgentIdentity
from app.modules.guard.models import GuardMemberConfig


def seed(count):
    workspace_id = uuid.uuid4()
    owner = 'local_mcp_' + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    agents = []
    with SessionLocal() as db:
        db.add(Workspace(id=workspace_id, name='Local MCP Canary ' + str(workspace_id)[:8],
                         owner_id=owner, is_approved=True, plan='free'))
        db.flush()
        for i in range(count + 1):
            user_id = owner if i == count else 'local_mcp_' + uuid.uuid4().hex
            identity_id = str(uuid.uuid4())
            token = 'cond_agt_' + secrets.token_urlsafe(32)
            role = 'admin' if i == count else 'developer'
            db.add(User(email=user_id + '@example.invalid', clerk_id=user_id,
                        workspace_id=workspace_id, role=role))
            db.add(WorkspaceUser(workspace_id=workspace_id, clerk_user_id=user_id, role=role))
            db.add(AgentIdentity(
                id=identity_id, workspace_id=workspace_id, name=f'local-canary-{i}',
                provider='conduct', token_prefix=token[:13], token_encrypted=encrypt({'token': token}),
                token_type='cli', created_at=now, expires_at=now + timedelta(hours=1),
                owner_user_id=user_id, lifecycle_state='active',
            ))
            db.flush()
            db.add(GuardMemberConfig(workspace_id=workspace_id, clerk_user_id=user_id,
                                    member_token=secrets.token_urlsafe(32), agent_identity_id=identity_id))
            agents.append({'id': identity_id, 'token': token})
        db.commit()
        # A provisioned workspace must have Guard installed before either MCP
        # endpoint runs; only the legacy endpoint auto-installs it on first use.
        from app.modules.guard.routers.config import _get_or_create_config
        _get_or_create_config(db, str(workspace_id))
    return {'workspace_id': str(workspace_id), 'agents': agents[:-1], 'observer': agents[-1]}


def revoke(workspace_id):
    with SessionLocal() as db:
        workspace = db.get(Workspace, uuid.UUID(workspace_id))
        if workspace is None or not workspace.name.startswith('Local MCP Canary '):
            raise ValueError('Not a canary-owned workspace')
        db.query(AgentIdentity).filter(AgentIdentity.workspace_id == workspace.id).update(
            {'lifecycle_state': 'deactivated'}, synchronize_session=False)
        db.query(GuardMemberConfig).filter(GuardMemberConfig.workspace_id == workspace.id).update(
            {'active': False}, synchronize_session=False)
        db.commit()
    return {'revoked': True}


if __name__ == '__main__':
    request = json.loads(sys.stdin.read())
    result = seed(request['agents']) if request['action'] == 'seed' else revoke(request['workspace_id'])
    print(json.dumps(result))
