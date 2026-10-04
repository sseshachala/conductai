"""Local, workspace-scoped labels for credential identities."""
import re

from app.core.config import settings
from app.models.workspace_user import WorkspaceUser


def agent_options(db, workspace_id: str, agents: list) -> list[dict[str, str]]:
    auto_users = {}
    for agent in agents:
        match = re.fullmatch(r"((?:user_|oidc_)[A-Za-z0-9_-]+) \(auto\)", agent.name.strip())
        if match:
            auto_users[str(agent.id)] = match.group(1)
    names = {}
    if auto_users:
        user_ids = sorted(set(auto_users.values()))
        if settings.auth_mode == "proxy":
            from app.modules.auth.console.models import ConsoleIdentityMapping
            members = db.query(ConsoleIdentityMapping.user_id, ConsoleIdentityMapping.display_name).join(
                WorkspaceUser, WorkspaceUser.clerk_user_id == ConsoleIdentityMapping.user_id,
            ).filter(
                WorkspaceUser.workspace_id == workspace_id,
                ConsoleIdentityMapping.issuer == settings.console_oidc_issuer,
                ConsoleIdentityMapping.user_id.in_(user_ids),
            ).all()
            names = {member.user_id: member.display_name.strip() for member in members if member.display_name}
        else:
            from app.models.user import User
            members = db.query(User.clerk_id, User.email).join(
                WorkspaceUser, WorkspaceUser.clerk_user_id == User.clerk_id,
            ).filter(WorkspaceUser.workspace_id == workspace_id, User.clerk_id.in_(user_ids)).all()
            names = {member.clerk_id: member.email.strip() for member in members if member.email}
    return [{"id": str(agent.id), "name": (
        f"{names[auto_users[str(agent.id)]]} (auto)" if names.get(auto_users.get(str(agent.id)))
        else "Auto-provisioned agent" if str(agent.id) in auto_users else agent.name
    )} for agent in agents]
