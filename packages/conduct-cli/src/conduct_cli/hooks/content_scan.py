"""Indirect prompt-injection scan of tool output (#2384).

PostToolUse sees what a tool returned to the model. Rules synced from the
server that declare ``match_content_source`` containing ``tool_result`` (the
same rules the Gateway applies to ``role:"tool"`` content) are evaluated here
against ``tool_response``.

A hook cannot un-run a tool, so the action is: record a warn event, mark the
session, and, when the rule's action is ``block``, deny the *next* tool call in
that session once (PreToolUse calls ``take_session_block``).

Stdlib only; Python 3.9 compatible. Never raises into the hook.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from conduct_cli.hooks.base import GUARD_DIR
from conduct_cli.hooks.policy_scan import _decoded_variants

CONTENT_SOURCE = "tool_result"
FLAGS_PATH = GUARD_DIR / "tool_content_flags.json"
_MAX_SCAN_CHARS = 256_000
_MAX_EXCERPT = 120
_FLAG_TTL_SECONDS = 6 * 3600
_MAX_SESSIONS = 50


def response_text(tool_response: Any) -> str:
    """Flatten a hook ``tool_response`` (str, dict or list) to scannable text."""
    parts = []  # type: List[str]

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 6 or sum(len(p) for p in parts) > _MAX_SCAN_CHARS:
            return
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value, depth + 1)

    walk(tool_response)
    return "\n".join(parts)[:_MAX_SCAN_CHARS]


def tool_result_rules(rules: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for rule in rules:
        declared = rule.get("match_content_source")
        if isinstance(declared, str):
            declared = [declared]
        if isinstance(declared, list) and CONTENT_SOURCE in declared and rule.get("match_pattern"):
            out.append(rule)
    return out


_ACTION_RANK = {"audit": 0, "allow": 0, "warn": 1, "approval": 2, "block": 3}


def scan_tool_response(
    rules: Iterable[Dict[str, Any]], tool_response: Any
) -> Optional[Tuple[Dict[str, Any], str]]:
    """Return ``(rule, matched_excerpt)`` for the most severe matching rule, or None."""
    candidates = tool_result_rules(rules)
    if not candidates:
        return None
    text = response_text(tool_response)
    if not text.strip():
        return None
    variants = [text] + [v for v in _decoded_variants(text[:_MAX_SCAN_CHARS]) if v and v != text]
    best = None  # type: Optional[Tuple[Dict[str, Any], str]]
    for rule in candidates:
        try:
            pattern = re.compile(rule["match_pattern"], re.IGNORECASE)
        except re.error:
            continue
        for variant in variants:
            found = pattern.search(variant)
            if found:
                if best is None or _ACTION_RANK.get(rule.get("action", "warn"), 1) > _ACTION_RANK.get(
                    best[0].get("action", "warn"), 1
                ):
                    best = (rule, found.group(0)[:_MAX_EXCERPT])
                break
    return best


# ── session marker ───────────────────────────────────────────────────────────

def _read_flags() -> Dict[str, Any]:
    try:
        data = json.loads(FLAGS_PATH.read_text()) if FLAGS_PATH.exists() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_flags(data: Dict[str, Any]) -> None:
    try:
        GUARD_DIR.mkdir(parents=True, exist_ok=True)
        if len(data) > _MAX_SESSIONS:
            for key in sorted(data, key=lambda k: data[k].get("ts", 0))[: len(data) - _MAX_SESSIONS]:
                del data[key]
        FLAGS_PATH.write_text(json.dumps(data))
    except Exception:
        pass


def mark_session(session_id: Optional[str], rule_id: str, action: str, message: str, tool_name: str) -> None:
    """Record that this session received flagged tool output.

    ``blocks_next`` is set only when the rule's action is ``block``."""
    if not session_id:
        return
    data = _read_flags()
    data[session_id] = {
        "rule_id": rule_id,
        "action": action,
        "message": message[:300],
        "tool_name": tool_name[:100],
        "blocks_next": action == "block",
        "ts": time.time(),
    }
    _write_flags(data)


def take_session_block(session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """If the session has a pending block from flagged tool output, consume and
    return it (one-shot, so the user can review and continue); else None."""
    if not session_id:
        return None
    data = _read_flags()
    flag = data.get(session_id)
    if not isinstance(flag, dict) or not flag.get("blocks_next"):
        return None
    if time.time() - float(flag.get("ts", 0)) > _FLAG_TTL_SECONDS:
        del data[session_id]
        _write_flags(data)
        return None
    flag["blocks_next"] = False
    data[session_id] = flag
    _write_flags(data)
    return flag
