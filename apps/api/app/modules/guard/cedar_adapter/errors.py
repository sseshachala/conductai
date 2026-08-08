"""Error taxonomy for the Cedar adapter."""
from __future__ import annotations

from typing import Any


class CedarAdapterError(Exception):
    """Base class for all Cedar adapter errors."""

    def __init__(
        self,
        message: str,
        feature: str | None = None,
        snippet: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.feature = feature
        self.snippet = snippet
        self.hint = hint

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.__class__.__name__,
            "message": str(self),
            "feature": self.feature,
            "snippet": self.snippet,
            "hint": self.hint,
        }


class UnsupportedCedarFeature(CedarAdapterError):
    """Cedar construct that maps to no Guard equivalent (temporal, extension functions, etc.)."""


class InvalidCedarSyntax(CedarAdapterError):
    """Cedar policy is malformed or missing required fields."""


class CedarMappingAmbiguity(CedarAdapterError):
    """Cedar policy is valid but has multiple possible Guard translations."""
