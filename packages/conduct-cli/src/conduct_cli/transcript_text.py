"""Transcript -> learnings text for team memory, one extractor per adapter `usage` format.

Each extractor returns ``["role: text", ...]`` for human and assistant prose only
(no tool output, no reasoning, no injected developer/system context). Only the
file tail is read: the summary uses the last messages, and Codex/Copilot logs
can be hundreds of MB.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

TAIL_BYTES = 4 * 1024 * 1024
MAX_MESSAGES = 60
MAX_CHARS = 12000
_MSG_CHARS = 500


def _records(path: Path) -> Iterator[dict]:
    """Yield JSON objects from the last TAIL_BYTES of a JSONL file (UTF-8, never raises)."""
    try:
        with path.open("rb") as stream:
            size = stream.seek(0, 2)
            start = max(0, size - TAIL_BYTES)
            stream.seek(start)
            if start:
                stream.readline()  # Drop the partial first line.
            data = stream.read()
    except OSError:
        return
    for line in data.decode("utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            yield record


def _line(role: str, text) -> str | None:
    if isinstance(text, str) and text.strip():
        return f"{role}: {text.strip()[:_MSG_CHARS]}"
    return None


def _claude(path: Path) -> list[str]:
    out = []
    for record in _records(path):
        msg = record.get("message")
        if not isinstance(msg, dict) or msg.get("role") not in ("user", "assistant"):
            continue
        content = msg.get("content")
        parts = content if isinstance(content, list) else [{"type": "text", "text": content}]
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                line = _line(msg["role"], part.get("text"))
                if line:
                    out.append(line)
    return out


def _codex(path: Path) -> list[str]:
    out = []
    for record in _records(path):
        payload = record.get("payload")
        if record.get("type") != "response_item" or not isinstance(payload, dict):
            continue
        if payload.get("type") != "message" or payload.get("role") not in ("user", "assistant"):
            continue  # developer/system messages are tooling, not conversation
        for part in payload.get("content") or []:
            if not isinstance(part, dict) or part.get("type") not in ("input_text", "output_text"):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.lstrip().startswith("<"):
                continue  # Injected <environment_context>/<user_instructions> blocks.
            line = _line(payload["role"], text)
            if line:
                out.append(line)
    return out


def _copilot(path: Path) -> list[str]:
    out = []
    roles = {"user.message": "user", "assistant.message": "assistant"}
    for record in _records(path):
        role = roles.get(record.get("type"))
        data = record.get("data")
        if role and isinstance(data, dict):
            line = _line(role, data.get("content"))
            if line:
                out.append(line)
    return out


EXTRACTORS: dict[str, Callable[[Path], list[str]]] = {
    "claude-jsonl": _claude,
    "codex-jsonl": _codex,
    "copilot-jsonl": _copilot,
}


def transcript_format(surface: str | None) -> str | None:
    """Adapter `usage` format for a hook surface, or None when it has no known transcript."""
    from conduct_cli.tool_adapters import ADAPTERS
    adapter = ADAPTERS.get("codex" if (surface or "").startswith("codex") else surface or "")
    return adapter.usage if adapter and adapter.usage in EXTRACTORS else None


def resolve_transcript(fmt: str, session_id: str, transcript_path: str | None) -> Path | None:
    """Locate the transcript via the same lookups the usage collectors use."""
    try:
        if fmt == "copilot-jsonl":
            from conduct_cli.hooks.copilot_usage import events_path
            return events_path(session_id)
        from conduct_cli.hooks.session_usage import transcript
        surface = "codex" if fmt == "codex-jsonl" else "claude-code"
        return transcript({"session_id": session_id, "transcript_path": transcript_path}, surface)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def learnings_text(fmt: str | None, session_id: str, transcript_path: str | None) -> str | None:
    """Last MAX_MESSAGES conversation lines joined for summarisation; None for unknown formats."""
    extractor = EXTRACTORS.get(fmt or "")
    if extractor is None:
        return None
    path = resolve_transcript(fmt, session_id, transcript_path)
    if path is None or not path.is_file():
        return None
    messages = extractor(path)
    return "\n\n".join(messages[-MAX_MESSAGES:])[:MAX_CHARS] if messages else None
