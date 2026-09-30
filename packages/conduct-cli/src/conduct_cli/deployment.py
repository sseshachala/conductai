"""Deployment endpoints shared by CLI commands, generated configs, and hooks."""
from dataclasses import dataclass
from urllib.parse import urlsplit

from .login_config import origin

SAAS_API = "https://api.conductai.ai"
SAAS_WEB = "https://app.conductai.ai"
SAAS_GATEWAY = "https://gateway.conductai.ai/gateway/v1"


def api_url(config: dict) -> str:
    return origin(config.get("api_url") or config.get("server") or SAAS_API)


def service_url(value: str, api: str) -> str:
    parsed = urlsplit(value)
    origin(f"{parsed.scheme}://{parsed.netloc}")
    if (parsed.query or parsed.fragment or any(c.isspace() for c in value)
            or any(c in value for c in "\\\"'`$")
            or any(p in (".", "..") for p in parsed.path.split("/"))):
        raise ValueError("Service endpoints must not contain credentials, queries, fragments, or traversal")
    hostname = parsed.hostname or ""
    if api != SAAS_API and (hostname == "conductai.ai" or hostname.endswith(".conductai.ai")):
        raise ValueError("A custom deployment cannot use a Conduct SaaS service endpoint")
    return value.rstrip("/")


@dataclass(frozen=True)
class Deployment:
    api: str
    web: str | None
    gateway: str | None
    mcp: str


def resolve(config: dict) -> Deployment:
    api = api_url(config)
    web = config.get("web_url") or (SAAS_WEB if api == SAAS_API else None)
    gateway = config.get("gateway_url") or config.get("proxy_url")
    if not gateway and api == SAAS_API:
        gateway = SAAS_GATEWAY
    # /mcp is a supported API route; a separate MCP origin is optional.
    mcp = config.get("mcp_url") or api + "/mcp"
    return Deployment(api, service_url(web, api) if web else None,
                      service_url(gateway, api) if gateway else None, service_url(mcp, api))


def gateway_from_metadata(config: dict, metadata: dict) -> str | None:
    """Custom servers never inherit the hosted Gateway when metadata is absent."""
    deployment = resolve(config)
    if config.get("gateway_url") or config.get("proxy_url"):
        return deployment.gateway
    candidate = metadata.get("conduct_proxy_url")
    if not candidate:
        return deployment.gateway
    if candidate.rstrip("/").endswith("/proxy"):
        candidate = candidate.rstrip("/")[:-len("/proxy")] + "/gateway/v1"
    return service_url(candidate, deployment.api)
