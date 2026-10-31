"""Outbound URL validation shared by every server-side egress path.

``validate_outbound_url`` is the single check used before the API connects to
a URL that a workspace admin or run state can influence (output-block
webhooks, gateway upstream overrides, gateway profile endpoints).

Rules:
- scheme must be https; http is accepted only in local/development
  (``settings.is_local_environment``) or for an allowlisted host.
- the hostname is resolved and EVERY resolved address must be public. Private,
  loopback, link-local, multicast, reserved, unspecified, CGNAT (100.64/10)
  and cloud-metadata addresses are refused, including IPv4-mapped IPv6 forms.
- hosts listed in ``settings.egress_allowed_hosts`` skip the address checks
  and may use http (escape hatch for self-hosted installs that target internal
  services). It is an explicit per-host allowlist, not a global off switch.

Residual risk (DNS rebinding): callers validate and then connect by hostname,
so a hostname that re-resolves between the check and the connect is not
caught. Callers must also not follow redirects (or must re-validate each hop).
A full fix pins the resolved address in a custom transport; the resolved
addresses are returned to make that possible.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import settings

_METADATA_ADDRS = frozenset({
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("fd00:ec2::254"),
})
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


class EgressBlocked(ValueError):
    """Raised when an outbound URL fails validation."""


def _unwrap(ip):
    """Return the embedded IPv4 for IPv4-mapped / NAT64 IPv6 addresses."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return ip.ipv4_mapped
        if ip in _NAT64:
            return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip


def is_blocked_address(ip) -> bool:
    """True when ``ip`` is not a public unicast address."""
    ip = _unwrap(ip)
    if ip in _METADATA_ADDRS:
        return True
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT:
        return True
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified or not ip.is_global
    )


def _allowed_hosts() -> set[str]:
    return {h.strip().lower() for h in (settings.egress_allowed_hosts or []) if h.strip()}


def validate_outbound_url(url: str, *, allow_unresolvable: bool = False) -> list[str]:
    """Validate ``url`` for outbound use. Returns the resolved addresses.

    Raises ``EgressBlocked`` on any violation. ``allow_unresolvable`` is for
    config-time checks where DNS may be unavailable (publish/CI); connect-time
    callers leave it False so unresolvable hosts fail closed.
    """
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").strip().split("%", 1)[0].lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise EgressBlocked(f"outbound URL malformed: {exc}") from exc
    scheme = (parsed.scheme or "").lower()
    if not host:
        raise EgressBlocked("outbound URL has no hostname")
    allowlisted = host in _allowed_hosts()
    # http only in local/dev, or for an explicitly allowlisted host (in-cluster
    # model services such as http://litellm.<ns>.svc:4000 are usually plain http).
    if scheme != "https" and not (scheme == "http" and (settings.is_local_environment or allowlisted)):
        raise EgressBlocked("outbound URL must use https")

    try:
        addrs = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(
                host, port or (443 if scheme == "https" else 80), type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            if allowlisted or allow_unresolvable:
                return []
            raise EgressBlocked(f"outbound host {host!r} could not be resolved") from exc
        addrs = []
        for info in infos:
            try:
                addrs.append(ipaddress.ip_address(str(info[4][0]).split("%", 1)[0]))
            except ValueError as exc:
                raise EgressBlocked(f"outbound host {host!r} resolved to an invalid address") from exc
        if not addrs:
            if allowlisted or allow_unresolvable:
                return []
            raise EgressBlocked(f"outbound host {host!r} did not resolve")

    if not allowlisted:
        for ip in addrs:
            if is_blocked_address(ip):
                raise EgressBlocked(f"outbound host {host!r} resolves to a non-public address; refused")
    return [str(a) for a in addrs]
