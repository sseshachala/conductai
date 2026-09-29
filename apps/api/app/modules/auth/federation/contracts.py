"""Internal post-verification context, never a client-authored authorization grant.

Schema validation checks structure, not signatures, membership or permissions.
Only the future trusted resolver may construct this context at request ingress.
"""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=512, pattern=r"\S")]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CallingIntegration(ContractModel):
    workspace_id: UUID
    agent_identity_id: UUID


class ExternalPrincipal(ContractModel):
    workspace_id: UUID
    principal_id: UUID
    kind: Literal["human", "workload"]
    issuer: Identifier
    subject: Identifier


class VerifiedAttribute(ContractModel):
    """Allowlisted mapping output, not an unfiltered token claims dictionary."""

    name: Identifier
    values: tuple[Identifier, ...]
    source_claim: Identifier


class VerificationEvidence(ContractModel):
    workspace_id: UUID
    connection_id: UUID
    issuer: Identifier
    subject: Identifier
    method: Literal["oauth_access_token", "integration_assertion"]
    audience: Identifier
    verified_at: AwareDatetime
    expires_at: AwareDatetime
    mapping_version: Identifier

    @model_validator(mode="after")
    def valid_interval(self):
        if self.expires_at <= self.verified_at:
            raise ValueError("identity evidence must expire after verification")
        return self


class DelegationBinding(ContractModel):
    """Reference to a checked grant; does not replace live grant authorization."""

    workspace_id: UUID
    grant_id: UUID
    caller_agent_identity_id: UUID
    principal_id: UUID
    actions: tuple[Identifier, ...] = Field(min_length=1)
    resources: tuple[Identifier, ...] = Field(min_length=1)


class ContextBase(ContractModel):
    schema_version: Literal[1] = 1
    workspace_id: UUID
    caller: CallingIntegration
    request_id: Identifier
    run_id: UUID | None = None

    @model_validator(mode="after")
    def caller_workspace_matches(self):
        if self.caller.workspace_id != self.workspace_id:
            raise ValueError("caller workspace mismatch")
        return self


class ServiceIdentityContext(ContextBase):
    mode: Literal["service_only"]


class DelegatedIdentityContext(ContextBase):
    mode: Literal["delegated"]
    principal: ExternalPrincipal
    delegation: DelegationBinding
    evidence: VerificationEvidence
    attributes: tuple[VerifiedAttribute, ...] = ()

    @model_validator(mode="after")
    def delegation_matches(self):
        if self.principal.workspace_id != self.workspace_id or self.delegation.workspace_id != self.workspace_id:
            raise ValueError("delegation workspace mismatch")
        if self.delegation.caller_agent_identity_id != self.caller.agent_identity_id:
            raise ValueError("delegation caller mismatch")
        if self.delegation.principal_id != self.principal.principal_id:
            raise ValueError("delegation principal mismatch")
        if self.evidence.workspace_id != self.workspace_id:
            raise ValueError("evidence workspace mismatch")
        if (self.evidence.issuer, self.evidence.subject) != (self.principal.issuer, self.principal.subject):
            raise ValueError("evidence principal mismatch")
        names = [attribute.name for attribute in self.attributes]
        if len(names) != len(set(names)):
            raise ValueError("duplicate mapped attribute")
        return self


ResolvedIdentityContext = Annotated[
    ServiceIdentityContext | DelegatedIdentityContext, Field(discriminator="mode")
]
