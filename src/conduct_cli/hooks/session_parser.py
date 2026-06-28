"""Session parser — extracts intent and tool sequence from AI session files.

Supports Claude Code (claude_code_v1) and Codex CLI (codex_v1).
All parsing is best-effort: any failure sets status="failed" and never raises.
stdlib only — no third-party dependencies.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

_INTENT_MAX = 300
_TOOL_SEQ_MAX = 200


@dataclass
class SessionData:
    intent: str | None
    tool_sequence: list[str]
    status: Literal["ok", "partial", "failed", "unsupported"]
    parser: str  # "claude_code_v1" | "codex_v1"


def _truncate(s: str, n: int) -> str:
    return s[:n] if len(s) > n else s


# ── Claude Code parser ────────────────────────────────────────────────────────

class _ClaudeCodeParser:
    """Parses ~/.claude/projects/<cwd-hash>/<session_id>.jsonl"""

    PARSER_ID = "claude_code_v1"

    def _find_session_file(self, session_id: str, cwd: str | None) -> Path | None:
        projects_root = Path.home() / ".claude" / "projects"
        if not projects_root.exists():
            return None

        # If cwd is given, derive the hash directory name Claude Code uses.
        # Claude Code encodes the cwd as a URL-encoded-like path replacing / with -.
        # Try direct match first, then scan all project dirs.
        candidates: list[Path] = []
        if cwd:
            # Claude Code replaces path separators with hyphens and strips leading separator
            slug = cwd.lstrip("/").replace("/", "-")
            d = projects_root / slug
            if d.is_dir():
                candidates.append(d)

        # Fall back: scan all subdirectories
        if not candidates:
            try:
                candidates = [p for p in projects_root.iterdir() if p.is_dir()]
            except Exception:
                return None

        for d in candidates:
            f = d / f"{session_id}.jsonl"
            if f.exists():
                return f

        return None

    def parse(self, session_id: str, cwd: str | None) -> SessionData:
        try:
            session_file = self._find_session_file(session_id, cwd)
            if session_file is None:
                return SessionData(intent=None, tool_sequence=[], status="failed", parser=self.PARSER_ID)

            intent: str | None = None
            tool_sequence: list[str] = []
            partial = False

            for raw_line in session_file.read_text(errors="ignore").splitlines():
                if not raw_line.strip():
                    continue
                try:
                    entry = json.loads(raw_line)
                except Exception:
                    partial = True
                    continue

                msg = entry.get("message", {})
                if not isinstance(msg, dict):
                    continue

                role = msg.get("role")
                content = msg.get("content")

                # Extract first human message as intent
                if intent is None and role == "user":
                    if isinstance(content, str) and content.strip():
                        intent = _truncate(content.strip(), _INTENT_MAX)
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "").strip()
                                if text:
                                    intent = _truncate(text, _INTENT_MAX)
                                    break

                # Collect tool_use names from assistant messages
                if role == "assistant" and isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            name = block.get("name")
                            if name and len(tool_sequence) < _TOOL_SEQ_MAX:
                                tool_sequence.append(name)

            status: Literal["ok", "partial", "failed", "unsupported"] = "partial" if partial else "ok"
            return SessionData(
                intent=intent,
                tool_sequence=tool_sequence,
                status=status,
                parser=self.PARSER_ID,
            )
        except Exception:
            return SessionData(intent=None, tool_sequence=[], status="failed", parser=self.PARSER_ID)


# ── Codex parser ──────────────────────────────────────────────────────────────

class _CodexParser:
    """Parses ~/.codex/sessions/<yyyy>/<MM>/<dd>/rollout-<ts>-<uuid>.jsonl
    Intent comes from ~/.codex/session_index.jsonl (thread_name field).
    """

    PARSER_ID = "codex_v1"

    def _get_intent_from_index(self, session_id: str) -> str | None:
        index_file = Path.home() / ".codex" / "session_index.jsonl"
        if not index_file.exists():
            return None
        try:
            for raw_line in index_file.read_text(errors="ignore").splitlines():
                if not raw_line.strip():
                    continue
                try:
                    entry = json.loads(raw_line)
                except Exception:
                    continue
                if entry.get("id") == session_id:
                    name = entry.get("thread_name", "").strip()
                    return _truncate(name, _INTENT_MAX) if name else None
        except Exception:
            pass
        return None

    def _find_session_file(self, session_id: str) -> Path | None:
        sessions_root = Path.home() / ".codex" / "sessions"
        if not sessions_root.exists():
            return None
        try:
            # Walk all date-partitioned subdirectories
            for f in sessions_root.rglob(f"*{session_id}*.jsonl"):
                return f
        except Exception:
            pass
        return None

    def parse(self, session_id: str, cwd: str | None) -> SessionData:
        try:
            intent = self._get_intent_from_index(session_id)
            session_file = self._find_session_file(session_id)
            if session_file is None:
                # Intent from index alone is still useful
                status: Literal["ok", "partial", "failed", "unsupported"] = "partial" if intent else "failed"
                return SessionData(intent=intent, tool_sequence=[], status=status, parser=self.PARSER_ID)

            tool_sequence: list[str] = []
            partial = False

            for raw_line in session_file.read_text(errors="ignore").splitlines():
                if not raw_line.strip():
                    continue
                try:
                    entry = json.loads(raw_line)
                except Exception:
                    partial = True
                    continue

                # Codex emits {"type": "tool_call", "name": "..."} entries
                if entry.get("type") == "tool_call":
                    name = entry.get("name") or entry.get("tool")
                    if name and len(tool_sequence) < _TOOL_SEQ_MAX:
                        tool_sequence.append(name)

            status = "partial" if partial else "ok"
            return SessionData(
                intent=intent,
                tool_sequence=tool_sequence,
                status=status,
                parser=self.PARSER_ID,
            )
        except Exception:
            return SessionData(intent=None, tool_sequence=[], status="failed", parser=self.PARSER_ID)


# ── Dispatcher ────────────────────────────────────────────────────────────────

_PARSERS: dict[str, "_ClaudeCodeParser | _CodexParser"] = {
    "claude_code": _ClaudeCodeParser(),
    "claude-code": _ClaudeCodeParser(),
    "codex": _CodexParser(),
    "codex_cli": _CodexParser(),
}


def parse_session(ai_tool: str, session_id: str, cwd: str | None = None) -> SessionData:
    """Dispatcher: returns SessionData for the given ai_tool.

    Never raises. Unknown tools return status="unsupported".
    """
    parser = _PARSERS.get(ai_tool)
    if parser is None:
        return SessionData(
            intent=None,
            tool_sequence=[],
            status="unsupported",
            parser=ai_tool or "unknown",
        )
    return parser.parse(session_id, cwd)
