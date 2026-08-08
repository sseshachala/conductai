"""Cedar policy adapter for Guard.

Converts Cedar policies (JSON representation) into Guard's native JSON pack format.
Runtime evaluation stays in policy_engine.py on our JSON format.

See docs/cedar-adapter-spec.md for the full mapping table and error taxonomy.

Phase 0 shipped: spec + error taxonomy. Mapper implementation pending (#1048 blocked).
"""
from __future__ import annotations

from app.modules.guard.cedar_adapter.errors import (
    CedarAdapterError,
    UnsupportedCedarFeature,
    InvalidCedarSyntax,
    CedarMappingAmbiguity,
)

__all__ = [
    "CedarAdapterError",
    "UnsupportedCedarFeature",
    "InvalidCedarSyntax",
    "CedarMappingAmbiguity",
]
