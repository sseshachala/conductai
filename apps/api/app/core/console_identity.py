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


def console_identity(claims: Mapping | None, *, mode: str, clerk_issuer: str) -> ConsoleIdentity:
    if mode != "proxy":
        return clerk_identity(claims, clerk_issuer)
    if not claims or not all(isinstance(claims.get(key), str) and claims[key]
                             for key in ("sub", "external_subject", "external_issuer")):
        raise HTTPException(401, "Invalid console identity")
    return ConsoleIdentity(provider="proxy", issuer=claims["external_issuer"],
                           subject=claims["external_subject"], user_id=claims["sub"])
