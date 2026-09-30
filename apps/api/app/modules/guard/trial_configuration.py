"""Deployment readiness for the existing Anthropic Try Guard demo."""
import os
from urllib.parse import urlsplit


def setup_reason(settings) -> str | None:
    if settings.auth_mode != "proxy":
        return None
    gateway = urlsplit(settings.conduct_proxy_url)
    host = gateway.hostname or ""
    if (not host or host == "conductai.ai" or host.endswith(".conductai.ai")
            or gateway.username or gateway.password or gateway.query or gateway.fragment
            or gateway.scheme not in ("http", "https")):
        return "deployment_gateway_required"
    if not os.environ.get("GUARD_TRIAL_ANTHROPIC_KEY", "").strip():
        return "deployment_provider_required"
    return None
