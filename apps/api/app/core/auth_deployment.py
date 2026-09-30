"""Deployment authentication policy, independent of web and worker entrypoints."""
from typing import Literal, Protocol

from fastapi import HTTPException

AuthMode = Literal["clerk", "development", "proxy"]
LOCAL_ENVIRONMENTS = frozenset({"local", "development"})


class AuthSettings(Protocol):
    auth_mode: AuthMode
    environment: str
    clerk_secret_key: str
    clerk_frontend_api: str


def validate_auth_mode(config: AuthSettings) -> None:
    if config.auth_mode not in ("clerk", "development", "proxy"):
        raise ValueError("Unsupported AUTH_MODE")
    if config.auth_mode == "development" and config.environment not in LOCAL_ENVIRONMENTS:
        raise ValueError("AUTH_MODE=development is permitted only in local/development environments")
    if config.auth_mode == "proxy":
        raise ValueError("AUTH_MODE=proxy is not available until the trusted console identity adapter is installed")


def validate_api_auth(config: AuthSettings) -> None:
    """Run before serving HTTP; workers do not need browser credentials."""
    validate_auth_mode(config)
    if config.auth_mode == "clerk" and not (
        config.clerk_secret_key.strip() and config.clerk_frontend_api.strip()
    ):
        raise ValueError("AUTH_MODE=clerk requires CLERK_SECRET_KEY and CLERK_FRONTEND_API")


def development_auth_enabled() -> bool:
    from app.core.config import settings

    try:
        validate_auth_mode(settings)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Authentication configuration invalid") from exc
    return settings.auth_mode == "development"
