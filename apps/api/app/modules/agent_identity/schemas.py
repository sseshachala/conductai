from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentIdentityCreate(BaseModel):
    name: str
    environment_id: Optional[str] = None


class AgentIdentityOut(BaseModel):
    id:           str
    name:         str
    provider:     str
    token_prefix: str
    created_at:   datetime
    last_used_at: Optional[datetime]
    environment_id: Optional[str] = None
    # Phase 2 identity fields (nullable for legacy rows until backfill runs)
    source:              Optional[str] = None
    source_id:           Optional[str] = None
    platform_of_origin:  Optional[str] = None
    owner_user_id:       Optional[str] = None
    agent_role_id:       Optional[str] = None
    lifecycle_state:     Optional[str] = None
    last_certified_at:   Optional[datetime] = None
    certification_cadence_days: Optional[int] = None
    risk_tier:           Optional[str] = None
    deactivated_at:      Optional[datetime] = None


class AgentIdentityCreated(AgentIdentityOut):
    """Returned once at creation (or regeneration). `token` is the full plaintext — never stored."""
    token: str


class AgentIdentityPatch(BaseModel):
    """Update identity metadata. Only the token/credential fields are immutable."""
    owner_user_id:              Optional[str] = None
    risk_tier:                  Optional[str] = Field(None, description="tier_1 | tier_2 | tier_3")
    lifecycle_state:            Optional[str] = Field(None, description="active | pending_review | deactivated | expired")
    certification_cadence_days: Optional[int] = None
    platform_of_origin:         Optional[str] = None
    metadata:                   Optional[dict[str, Any]] = None


class ApiTokenCreate(BaseModel):
    name: str
    expires_in_days: Optional[int] = None  # None = never expires


class ApiTokenOut(BaseModel):
    id: str
    token_name: Optional[str]
    token_prefix: Optional[str]
    token_type: str
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class ApiTokenCreated(ApiTokenOut):
    token: str  # full token, shown once only
