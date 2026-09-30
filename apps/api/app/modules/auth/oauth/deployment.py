"""Browser and OAuth issuer URLs; proxy deployments must supply their own origins."""
import os
from urllib.parse import urlsplit

from app.core.config import settings


def configured_url(name: str, clerk_default: str) -> str:
    value = os.getenv(name)
    if settings.auth_mode != "proxy":
        return value or clerk_default
    if not value:
        raise ValueError(f"AUTH_MODE=proxy requires {name}")
    url = urlsplit(value)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in ("", "/")):
        raise ValueError(f"{name} must be an HTTPS origin")
    return value.rstrip("/")


def web_url() -> str:
    return configured_url("CONDUCT_WEB_URL", "https://app.conductai.ai")


def issuer_url() -> str:
    return configured_url("CONDUCT_OAUTH_ISSUER", "https://api.conductai.ai")
