"""
Runtime — shared primitives + bound Runtime object.

Dependency order: runtime → tool_engine → dag_runner → executor

Module-level functions are used by tool_engine/dag_runner/executor.
Runtime class binds a RunContext + db session so callers don't thread
run_id/workspace_id through every call site.
"""
from __future__ import annotations

import functools
import re
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.runtime.run_contract import RunContext


# ── agent config ──────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _agent_config() -> dict:
    path = Path(__file__).parent / "agent_config.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


# ── time ──────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── redaction ─────────────────────────────────────────────────────────────────

_REDACT_PATTERNS = [
    # GitHub tokens
    (re.compile(r'ghp_[A-Za-z0-9]{36,}'), '[REDACTED-GITHUB-TOKEN]'),
    (re.compile(r'github_pat_[A-Za-z0-9_]{82,}'), '[REDACTED-GITHUB-TOKEN]'),
    (re.compile(r'ghs_[A-Za-z0-9]{36,}'), '[REDACTED-GITHUB-TOKEN]'),
    # Anthropic keys (sk-ant-api03-... contain dashes — must precede the generic sk- rule)
    (re.compile(r'sk-ant-[A-Za-z0-9_\-]{20,}'), '[REDACTED-ANTHROPIC-KEY]'),
    # OpenAI / generic sk- keys
    (re.compile(r'sk-[A-Za-z0-9]{32,}'), '[REDACTED-API-KEY]'),
    # Slack bot / user / app tokens
    (re.compile(r'xox[bpra]-[A-Za-z0-9\-]{10,}'), '[REDACTED-SLACK-TOKEN]'),
    # Bearer tokens in headers / strings
    (re.compile(r'Bearer\s+[A-Za-z0-9\-_\.]{20,}'), 'Bearer [REDACTED]'),
]


def _redact(text: str) -> str:
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _redact_payload(payload: dict) -> dict:
    """Recursively redact sensitive tokens from all string values in a payload."""
    out = {}
    for k, v in payload.items():
        if isinstance(v, str):
            out[k] = _redact(v)
        elif isinstance(v, dict):
            out[k] = _redact_payload(v)
        elif isinstance(v, list):
            out[k] = [_redact(i) if isinstance(i, str) else i for i in v]
        else:
            out[k] = v
    return out


# ── trace / event writers ─────────────────────────────────────────────────────

def _write_trace(db, run_id, block_id: str, turn: int, role: str, **kwargs) -> None:
    """Write one run_trace row. Fire-and-forget — never raises."""
    try:
        from app.models.run_trace import RunTrace
        db.add(RunTrace(run_id=run_id, block_id=block_id, turn=turn, role=role, **kwargs))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def _emit(db, run_id, block_id: str | None, kind: str, payload: dict):
    from app.models.run import RunEvent
    event = RunEvent(run_id=run_id, block_id=block_id, kind=kind, payload=_redact_payload(payload))
    db.add(event)
    db.commit()
    from app.routers.runs import publish_run_event
    publish_run_event(str(run_id))


# ── DAG state ref resolution ──────────────────────────────────────────────────

def _resolve_refs(value: Any, state: dict) -> Any:
    """Replace {{block_id.field}} references with values from run state.

    Grammar: matches `{{ident.dot.path}}` only — no filters (|default:), no
    conditionals ({% if %}). If you see a `|` or `%` inside `{{}}`, the whole
    match falls through and the literal template leaks into output. Track
    unresolved refs on state so callers can surface them as a run_event.
    """
    import re as _re

    if isinstance(value, str):
        _MISSING = object()
        unresolved = state.setdefault("__unresolved_template_refs", [])

        def replace(m):
            parts = m.group(1).split(".")
            obj = state.get(parts[0], _MISSING)
            if obj is _MISSING:
                unresolved.append(m.group(1))
                return m.group(0)
            for p in parts[1:]:
                if isinstance(obj, dict):
                    nxt = obj.get(p, _MISSING)
                    if nxt is _MISSING:
                        unresolved.append(m.group(1))
                        return m.group(0)
                    obj = nxt
                else:
                    # {{a.b.c}} where `a.b` is a non-dict (string, list, int).
                    # Can't walk further — record + leak literal.
                    unresolved.append(m.group(1))
                    return m.group(0)
            return str(obj)

        return _re.sub(r"\{\{([\w.]+)\}\}", replace, value)
    if isinstance(value, dict):
        return {k: _resolve_refs(v, state) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(i, state) for i in value]
    return value


# ── Runtime — bound context object ───────────────────────────────────────────

class Runtime:
    """
    Bound runtime: holds a RunContext + db session.

    Blocks and the DAG runner can use this instead of threading
    run_id/workspace_id through every call.  Module-level functions
    (_emit, _write_trace, etc.) remain for callers that aren't yet
    converted.
    """

    def __init__(self, ctx: "RunContext", db) -> None:
        self.ctx = ctx
        self.db = db

    # ── infra shortcuts ───────────────────────────────────────────────────────

    def emit(self, block_id: str | None, kind: str, payload: dict) -> None:
        _emit(self.db, self.ctx.run_id, block_id, kind, payload)

    def write_trace(self, block_id: str, turn: int, role: str, **kwargs) -> None:
        _write_trace(self.db, self.ctx.run_id, block_id, turn, role, **kwargs)

    # ── state helpers ─────────────────────────────────────────────────────────

    def resolve_refs(self, value: Any, state: dict) -> Any:
        return _resolve_refs(value, state)

    # ── config / time ─────────────────────────────────────────────────────────

    def agent_config(self) -> dict:
        return _agent_config()

    def now(self) -> datetime:
        return _now()

    # ── context properties ────────────────────────────────────────────────────

    @property
    def run_id(self) -> str:
        return self.ctx.run_id

    @property
    def workspace_id(self) -> str:
        return self.ctx.workspace_id
