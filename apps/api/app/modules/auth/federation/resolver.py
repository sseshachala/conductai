"""Application-neutral resolution. Only the trusted ingress supplies caller identity."""
from datetime import datetime, timezone
from uuid import UUID

from .config import TrustConfig
from .contracts import CallingIntegration, DelegatedIdentityContext, DelegationBinding, ExternalPrincipal
from .delegation_models import FederationCallerBinding, FederationGrant, FederationPrincipal
from .models import FederationConnection
from .network import VerificationUnavailable
from .verifier import InvalidIdentity, verify_access_token


class FederationDenied(Exception):
    def __init__(self, code, status=403):
        self.code, self.status = code, status
        super().__init__(code)


def fail(code, status=403):
    raise FederationDenied(code, status)


def _live(db, workspace, binding, principal, grant, action=None):
    now = datetime.now(timezone.utc)
    if binding.status != "active" or principal.status != "active":
        fail("federation_identity_disabled")
    if grant is None or grant.status != "active" or grant.expires_at <= now:
        fail("federation_grant_invalid")
    if any(row.workspace_id != workspace for row in (binding, principal, grant)):
        fail("federation_workspace_mismatch")
    if grant.binding_id != binding.id or grant.principal_id != principal.id:
        fail("federation_grant_mismatch")
    permitted = set(binding.actions) & set(principal.actions) & set(grant.actions)
    if not permitted or (action is not None and action not in permitted):
        fail("federation_action_forbidden")
    return (action,) if action else tuple(sorted(permitted))


def resolve(db, *, workspace: UUID, caller, connection_id: UUID | None,
            subject_token: str | None, request_id: str, action: str | None):
    binding = db.query(FederationCallerBinding).filter(
        FederationCallerBinding.workspace_id == workspace,
        FederationCallerBinding.caller_id == caller.id,
    ).first()
    if binding is None:
        if connection_id is not None or subject_token is not None:
            fail("federation_caller_not_bound")
        return None
    if binding.status != "active":
        fail("federation_binding_disabled")
    if connection_id is None or not subject_token:
        fail("federation_evidence_required", 401)
    if binding.connection_id != connection_id:
        fail("federation_connection_forbidden")
    connection = db.query(FederationConnection).filter(
        FederationConnection.workspace_id == workspace, FederationConnection.id == connection_id,
    ).first()
    if connection is None:
        fail("federation_connection_unavailable")
    config = TrustConfig.model_validate(connection.config)
    if config.status != "active":
        fail("federation_connection_disabled")
    try:
        verified = verify_access_token(subject_token, config, workspace_id=workspace,
                                       connection_id=connection.id, revision=connection.revision)
    except InvalidIdentity:
        fail("federation_invalid_evidence", 401)
    except VerificationUnavailable:
        fail("federation_verification_unavailable", 503)
    principal = db.query(FederationPrincipal).filter(
        FederationPrincipal.workspace_id == workspace,
        FederationPrincipal.issuer == verified.evidence.issuer,
        FederationPrincipal.subject == verified.evidence.subject,
    ).first()
    if principal is None:
        fail("federation_principal_not_approved")
    grant = db.query(FederationGrant).filter(
        FederationGrant.workspace_id == workspace, FederationGrant.binding_id == binding.id,
        FederationGrant.principal_id == principal.id,
    ).first()
    actions = _live(db, workspace, binding, principal, grant, action)
    return DelegatedIdentityContext(
        mode="delegated", workspace_id=workspace, request_id=request_id,
        caller=CallingIntegration(workspace_id=workspace, agent_identity_id=UUID(caller.id)),
        principal=ExternalPrincipal(workspace_id=workspace, principal_id=principal.id,
                                    issuer=principal.issuer, subject=principal.subject, kind=principal.kind),
        delegation=DelegationBinding(workspace_id=workspace, grant_id=grant.id,
                                     caller_agent_identity_id=UUID(caller.id), principal_id=principal.id,
                                     actions=actions, resources=(f"workspace:{workspace}",)),
        evidence=verified.evidence, attributes=verified.attributes,
    )


def recheck(db, context, action):
    """Reauthorize at use; never treat a persisted context as perpetual authority."""
    from app.modules.agent_identity.models import AgentIdentity
    workspace = context.workspace_id
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace)
    if context.evidence.expires_at <= datetime.now(timezone.utc):
        fail("federation_evidence_expired", 401)
    caller = db.query(AgentIdentity).filter(AgentIdentity.workspace_id == workspace,
            AgentIdentity.id == str(context.caller.agent_identity_id)).populate_existing().first()
    if (caller is None or caller.lifecycle_state != "active" or caller.token_type != "api"
            or (caller.expires_at and caller.expires_at <= datetime.now(timezone.utc))):
        fail("federation_caller_inactive")
    connection = db.query(FederationConnection).filter(FederationConnection.workspace_id == workspace,
            FederationConnection.id == context.evidence.connection_id).populate_existing().first()
    if (connection is None or connection.config.get("status") != "active"
            or str(connection.revision) != context.evidence.mapping_version):
        fail("federation_connection_changed")
    binding = db.query(FederationCallerBinding).filter(FederationCallerBinding.workspace_id == workspace,
            FederationCallerBinding.caller_id == caller.id).populate_existing().first()
    principal = db.query(FederationPrincipal).filter(FederationPrincipal.workspace_id == workspace,
            FederationPrincipal.id == context.principal.principal_id).populate_existing().first()
    grant = db.query(FederationGrant).filter(FederationGrant.workspace_id == workspace,
            FederationGrant.id == context.delegation.grant_id).populate_existing().first()
    if binding is None or principal is None or binding.connection_id != connection.id:
        fail("federation_binding_invalid")
    if action not in context.delegation.actions or context.delegation.resources != (f"workspace:{workspace}",):
        fail("federation_action_forbidden")
    _live(db, workspace, binding, principal, grant, action)
