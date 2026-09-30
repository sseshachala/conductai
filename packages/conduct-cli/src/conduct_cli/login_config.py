"""Resolve explicit deployment endpoints without guessing console hostnames."""
from __future__ import annotations

from urllib.parse import urlsplit


def origin(value: str) -> str:
    value = value.rstrip("/")
    url = urlsplit(value)
    try:
        url.port
    except ValueError:
        raise ValueError("Invalid login endpoint port") from None
    if (not url.hostname or url.username or url.password or url.path or url.query
            or url.fragment or any(c.isspace() for c in value) or "\\" in value):
        raise ValueError("Login endpoints must be origins without paths, credentials, queries, or fragments")
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1")
    ):
        raise ValueError("Login endpoints require HTTPS (HTTP allowed only on loopback)")
    return value


def endpoints(args, config: dict, default_api: str, default_web: str) -> tuple[str, str | None]:
    api = origin(getattr(args, "server", None) or config.get("api_url") or config.get("server") or default_api)
    explicit_web = getattr(args, "web_url", None)
    same_server = api == origin(config.get("api_url") or config.get("server") or default_api)
    web = explicit_web or (config.get("web_url") if same_server else None)
    if not web and api == default_api:
        web = default_web
    if not web and not getattr(args, "token", None):
        raise ValueError("Custom servers require --web-url with the Conduct console origin")
    return api, origin(web) if web else None
