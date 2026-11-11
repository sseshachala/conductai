"""Tool-call correlation IDs (#2168).

The Conduct Gateway tags every response containing ``tool_calls[]`` with
``X-Conduct-Tool-Correlation-Ids: <tool_call_id>=<corr_id>,...`` (wire format:
docs/gateway/tool-correlation.md). This module mirrors the server-side
``parse_correlation_header`` so hooks can attach the correlation_id to the
tool-execution events they report.

Python 3.9 compatible. Never raises: correlation is best-effort metadata.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

HEADER_NAME = "X-Conduct-Tool-Correlation-Ids"
_CORRELATION_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_MAX_HEADER_LEN = 16384


def parse_correlation_header(header_value: Optional[str]) -> Dict[str, str]:
    """Return ``{tool_call_id: correlation_id}``; malformed pairs are dropped."""
    if not header_value or not isinstance(header_value, str):
        return {}
    out = {}  # type: Dict[str, str]
    for pair in header_value[:_MAX_HEADER_LEN].split(","):
        if "=" not in pair:
            continue
        key, val = pair.split("=", 1)
        key, val = key.strip(), val.strip()
        if key and _CORRELATION_ID_RE.match(val):
            out.setdefault(key, val)
    return out


def correlation_id_for_tool_use(data: Dict[str, Any]) -> Optional[str]:
    """Resolve the correlation_id for the tool execution described by hook ``data``.

    Looks, in order, at fields a surface may populate when it has seen the
    gateway response: ``conduct_tool_correlation_ids`` (mapping or header
    string), ``tool_correlation_ids``, ``correlation_id``. Claude Code and Codex
    hooks do not currently provide any of these (they talk to the gateway
    directly and the hook never sees response headers), so this returns None
    there; the API then resolves the id server-side from ``tool_use_id``.
    """
    try:
        tool_use_id = data.get("tool_use_id")
        direct = data.get("correlation_id")
        if isinstance(direct, str) and _CORRELATION_ID_RE.match(direct):
            return direct
        for key in ("conduct_tool_correlation_ids", "tool_correlation_ids"):
            raw = data.get(key)
            mapping = parse_correlation_header(raw) if isinstance(raw, str) else (
                raw if isinstance(raw, dict) else {}
            )
            if tool_use_id and isinstance(mapping, dict):
                val = mapping.get(tool_use_id)
                if isinstance(val, str) and _CORRELATION_ID_RE.match(val):
                    return val
    except Exception:
        pass
    return None
