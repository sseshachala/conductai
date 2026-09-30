"""Normalized console identity, separate from delegated runtime evidence."""
from dataclasses import dataclass
from typing import Literal, Mapping

from fastapi import HTTPException


@dataclass(frozen=True)
class ConsoleIdentity:
    provider: Literal["clerk", "proxy"]
    issuer: str
    subject: str
    user_id: str
    organization_id: str | None = None


def clerk_identity(claims: Mapping | None, issuer: str) -> ConsoleIdentity:
    """Normalize already-verified claims; never parse raw tokens or trust headers."""
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(status_code=401, detail="No user ID in token")
    organization = claims.get("org_id")
    return ConsoleIdentity(
        provider="clerk", issuer=issuer, subject=subject, user_id=subject,
        organization_id=organization if isinstance(organization, str) else None,
    )
