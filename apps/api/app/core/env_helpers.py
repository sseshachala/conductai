"""Small env-var parsers shared across cache modules.

Extracted so ``auth_cache``, ``effective_policy_cache``, and any future
cache built on the same pattern don't each carry a private copy that
drifts on edge cases (negative values, non-numeric strings, missing
keys).
"""
from __future__ import annotations

import os


def env_int(name: str, default: int, *, minimum: int = 0) -> int:
    """Parse ``os.environ[name]`` as int with a floor at ``minimum``.
    Falls back to ``default`` on missing key or non-numeric value."""
    try:
        return max(minimum, int(os.environ[name]))
    except (KeyError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    """Parse ``os.environ[name]`` as float. Falls back to ``default``
    on missing key or non-numeric value."""
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default
