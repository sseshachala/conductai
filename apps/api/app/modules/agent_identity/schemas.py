from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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


class AgentIdentityCreated(AgentIdentityOut):
    """Returned once at creation (or regeneration). `token` is the full plaintext — never stored."""
    token: str


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
