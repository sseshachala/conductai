"""EventSource transport adapter; authorization stays in the shared dependencies."""
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core import auth
from app.core.database import get_db


def stream_credentials(request: Request) -> HTTPAuthorizationCredentials | None:
    authorization = request.headers.get("authorization")
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        # Never fall back to query auth when an invalid header was supplied.
        return HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=token if scheme.lower() == "bearer" else "",
        )
    token = request.query_params.get("token")
    if token is None:
        return None
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def get_workspace_id_sse(request: Request, db: Session = Depends(get_db)) -> str:
    return auth.get_workspace_id(
        credentials=stream_credentials(request),
        ws_id=request.query_params.get("workspace_id"),
        x_workspace_id=request.headers.get("x-workspace-id"), db=db,
    )


def get_user_workspace_role_sse(
    request: Request,
    workspace_id: str = Depends(get_workspace_id_sse),
    db: Session = Depends(get_db),
) -> str:
    credentials = stream_credentials(request)
    user_id = auth.get_user_id(credentials=credentials, db=db)
    if user_id is None:
        return auth.check_permission(user_id=user_id, workspace_id=workspace_id,
                                     credentials=credentials, db=db, permission="platform.runs.view")
    return auth.get_user_workspace_role(user_id, workspace_id, db)
