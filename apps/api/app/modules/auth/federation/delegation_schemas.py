"""Explicit approval, exact actions, and workspace-only MCP policy-check scope."""
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from .contracts import ContractModel, Identifier

# Capabilities supported by this release, not customer-specific permissions.
Action = Literal["mcp.guard_check", "mcp.guard_check_prompt", "gateway.inference", "workflows.run"]


class ApprovalWrite(ContractModel):
    expected_revision: int = Field(ge=0, strict=True)
    status: Literal["active", "disabled"]
    actions: tuple[Action, ...] = Field(min_length=1, max_length=4)


class PrincipalWrite(ApprovalWrite):
    issuer: Identifier
    subject: Identifier
    kind: Literal["human", "workload"]


class BindingWrite(ApprovalWrite):
    caller_id: UUID
    connection_id: UUID


class GrantWrite(ApprovalWrite):
    binding_id: UUID
    principal_id: UUID
    expires_at: AwareDatetime
