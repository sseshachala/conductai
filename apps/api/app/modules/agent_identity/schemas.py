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
