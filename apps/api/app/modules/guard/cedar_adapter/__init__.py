"""Cedar policy adapter for Guard.

Converts Cedar policies (JSON representation) into Guard's native JSON pack format.
Runtime evaluation stays in policy_engine.py on our JSON format.

See docs/cedar-adapter-spec.md for the full mapping table and error taxonomy.
"""
from __future__ import annotations

from app.modules.guard.cedar_adapter.errors import (
    CedarAdapterError,
    UnsupportedCedarFeature,
    InvalidCedarSyntax,
    CedarMappingAmbiguity,
)
from app.modules.guard.cedar_adapter.mapper import (
    cedar_json_to_rule,
    cedar_json_bundle_to_pack,
)

__all__ = [
    "CedarAdapterError",
    "UnsupportedCedarFeature",
    "InvalidCedarSyntax",
    "CedarMappingAmbiguity",
    "cedar_json_to_rule",
    "cedar_json_bundle_to_pack",
]
