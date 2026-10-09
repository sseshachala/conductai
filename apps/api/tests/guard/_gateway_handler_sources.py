"""Source text of the Gateway request lifecycle, for source-pin tests (#2399).

``handle_gateway_request`` used to live in one function in
``gateway_handler.py``; source pins grepped that file. #2399 split the
lifecycle into phase modules, so the pins now read the handler plus every
phase module, in lifecycle order (position-based pins rely on the order).
"""
from __future__ import annotations

from pathlib import Path

_GUARD = Path(__file__).resolve().parents[2] / "app" / "modules" / "guard"

LIFECYCLE_MODULES = (
    "gateway_handler.py",
    "gateway_phase_ingress.py",
    "gateway_phase_routing.py",
    "gateway_phase_policy.py",
    "gateway_phase_upstream.py",
    "gateway_phase_reserve.py",
    "gateway_phase_dispatch.py",
    "gateway_phase_finalize.py",
    "gateway_phase_settle.py",
)


def gateway_lifecycle_source() -> str:
    """Concatenated source of ``gateway_handler.py`` and its phase modules."""
    return "\n".join((_GUARD / name).read_text(encoding="utf-8") for name in LIFECYCLE_MODULES)
