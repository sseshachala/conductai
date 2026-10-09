"""Brain block tool phase: tool catalogue and per-call dispatch.

Extracted from ``brain_block._execute_brain`` (#2400). ``ToolRunner``
dispatches one tool call: MCP tools (with the Guard check) or built-in
sandbox tools (with the Guard check and the require_tests_pass gate).
Rule matching lives in ``brain_guard``; verdict side effects too.
"""
from __future__ import annotations

import json

import structlog

from app.runtime.blocks.brain_guard import (
    match_builtin_rule,
    match_mcp_rule,
    record_runtime_guard_verdict as _record_guard_verdict,
)

# Same logger name as before the split so worker log routing is unchanged.
log = structlog.get_logger("app.runtime.blocks.brain_block")

# MCP tool naming — Anthropic tools API requires ^[a-zA-Z0-9_-]{1,128}$.
# Prior joins used `::` which fails validation and broke every workflow
# with MCP tools attached (self-driving-network-approval-demo regression,
# 2026-09-10). We sanitize both halves to that alphabet and join with `__`,
# and mirror the sanitization when building the server-name lookup map so
# tool_use responses route back correctly.
# ponytail: server.name authored to contain `__` will split ambiguously;
# document convention rather than encode a fully-reversible scheme.
_MCP_JOIN_SEP = "__"


def _mcp_safe_name(s: str) -> str:
    import re as _re
    return _re.sub(r"[^A-Za-z0-9_-]", "-", s or "")


# Also re-exported from brain_block for any caller that imports it there.
BRAIN_TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file at the given path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path to read"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file at the given path. Creates parent directories if needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write to the file"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_shell",
        "description": "Execute a shell command and return stdout/stderr. Use for tests, builds, git commands.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "working_dir": {"type": "string", "description": "Working directory (optional)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "search_code",
        "description": "Search for a pattern in files using grep. Returns matching lines with file paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory or file to search in", "default": "."},
                "file_glob": {"type": "string", "description": "File glob to filter (e.g. '*.py')", "default": "*"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "mark_complete",
        "description": (
            "Signal that the task is complete and return a structured result. "
            "Call this instead of stop_reason end_turn when you have a definitive outcome. "
            "Always pass a 'result' key summarising what was accomplished."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Summary of what was accomplished"},
                "output": {"type": "object", "description": "Optional structured output data"},
            },
            "required": ["result"],
        },
    },
]

_GIT_COMMIT_PATTERNS = ("git commit", "git push", "gh pr create")
_TEST_MARKERS = ("pytest", "npm test", "yarn test", "make test",
                 "go test", "cargo test", "rspec", "jest", "vitest")


def _classify_tool_error(result: str) -> str:
    """Prefix tool results with a structured error category for LLM signal."""
    if result.startswith("Refused:"):
        return f"[permission_denied] {result}"
    if "timed out" in result.lower() or "timeout" in result.lower():
        return f"[timeout] {result}"
    if result.startswith("Error:") or result.startswith("error:"):
        return f"[tool_error] {result}"
    return result


class ToolRunner:
    """Dispatches the agentic loop's tool calls for one brain block run."""

    def __init__(self, r, *, require_tests_pass: bool):
        self.r = r
        self.require_tests_pass = require_tests_pass
        # {server_name -> McpServer row}, populated lazily on first MCP call.
        self._mcp_server_cache: dict | None = None
        # Reset per turn by the loop; set True when a test command runs.
        self.test_ran_this_turn: bool = False

    def mcp_server_map(self) -> dict:
        if self._mcp_server_cache is not None:
            return self._mcp_server_cache
        self._mcp_server_cache = {}
        db, workspace_id = self.r.db, self.r.workspace_id
        if not db or not workspace_id:
            return self._mcp_server_cache
        try:
            from app.models.mcp_server import McpServer as _McpServer
            servers = db.query(_McpServer).filter(
                _McpServer.workspace_id == workspace_id
            ).all()
            for s in servers:
                # Key by the sanitized form used in tool names so the parse
                # round-trips. Retain raw name in the value for downstream use.
                self._mcp_server_cache[_mcp_safe_name(s.name)] = s
        except Exception as exc:
            log.warning("brain.mcp_dispatch.map_failed", error=str(exc))
        return self._mcp_server_cache

    def run(self, tc, turns: int) -> tuple[str, bool]:
        """Return ``(result_content, guard_blocked_mcp)``.

        ``guard_blocked_mcp`` means the caller records the result and
        skips the tool_result trace and brain_tool_call event, exactly as
        the inline loop did. A sandbox ``RuntimeError`` is emitted as
        ``modal_error`` and re-raised.
        """
        r = self.r
        try:
            if _MCP_JOIN_SEP in tc.name:
                return self._run_mcp(tc, turns)
            return self._run_builtin(tc, turns), False
        except RuntimeError as sandbox_err:
            if r.db and r.run_id:
                r.emit(r.db, r.run_id, r.block_id, "brain_tool_call", {
                    "tool": "modal_error",
                    "summary": str(sandbox_err),
                    "turn": turns,
                })
            raise

    def _apply_verdict(self, tc, turns: int, hit: dict, input_text: str) -> tuple[str, str, str | None]:
        """Emit the guard event and write the audit row; return (action, msg, rule_id)."""
        r = self.r
        _guard_action = hit.get("action", "audit")
        _guard_msg = hit.get("message", "")
        # _project_rule (mcp.py) renames id -> rule_id (#2401).
        # Also fall back to "id" for defence in depth.
        _guard_rule_id = hit.get("rule_id") or hit.get("id")
        # Emit to run event stream so the CLI + dashboard see it
        if r.db and r.run_id:
            r.emit(r.db, r.run_id, r.block_id, "brain_tool_call", {
                "tool": tc.name,
                "guard_action": _guard_action,
                "guard_rule": _guard_rule_id,
                "guard_message": _guard_msg,
                "turn": turns,
            })
        # Audit row (flight recorder) + block/warn fan-out.
        _record_guard_verdict(
            r.db, workspace_id=r.workspace_id, user_email=r.user_email,
            tool_name=tc.name, action=_guard_action,
            rule_id=_guard_rule_id, message=_guard_msg,
            input_text=input_text, run_id=r.run_id,
            playbook_slug=r.playbook_slug, workflow_id=r.workflow_id,
        )
        return _guard_action, _guard_msg, _guard_rule_id

    def _run_mcp(self, tc, turns: int) -> tuple[str, bool]:
        r = self.r
        db, workspace_id = r.db, r.workspace_id
        # MCP tool dispatch — server-name__tool-name (see _mcp_safe_name).
        _mcp_server_name, _mcp_tool_name = tc.name.split(_MCP_JOIN_SEP, 1)

        # Guard check before every MCP tool call
        if r.state.get("__guard_enabled") and db and workspace_id:
            try:
                from app.modules.guard.routers.mcp import _match_policy, _get_rules  # noqa: F401
                from app.modules.guard.tool_groups import tool_matches
                import uuid as _uuid
                _guard_rules = _get_rules(db, _uuid.UUID(workspace_id))

                # Evaluate match_mcp_server and match_tool against MCP calls
                _mcp_inp_text = json.dumps(tc.input)
                _guard_hit = match_mcp_rule(
                    _guard_rules, _mcp_server_name, _mcp_tool_name,
                    _mcp_inp_text, tool_matches,
                )
                if _guard_hit:
                    _guard_action, _guard_msg, _ = self._apply_verdict(
                        tc, turns, _guard_hit, _mcp_inp_text,
                    )
                    if _guard_action == "block":
                        return f"[guard_blocked] {_guard_msg}", True
            except Exception as _guard_exc:
                log.warning("brain.mcp_dispatch.guard_failed", error=str(_guard_exc))

        _mcp_map = self.mcp_server_map()
        _mcp_server_row = _mcp_map.get(_mcp_server_name)
        if not _mcp_server_row:
            result_content = f"[mcp_error] MCP server '{_mcp_server_name}' not found in workspace"
        else:
            try:
                from app.core.crypto import decrypt as _decrypt
                from app.runtime.integrations import mcp_client as _mcp_client
                _mcp_token = (
                    _decrypt(_mcp_server_row.encrypted_auth).get("token")
                    if _mcp_server_row.encrypted_auth else None
                )
                _mcp_result = _mcp_client.call_tool(
                    _mcp_server_row.url,
                    _mcp_token,
                    _mcp_tool_name,
                    tc.input or {},
                    transport=_mcp_server_row.transport or "auto",
                )
                if isinstance(_mcp_result, dict):
                    result_content = json.dumps(_mcp_result)
                else:
                    result_content = str(_mcp_result)
            except Exception as _mcp_exc:
                result_content = f"[mcp_error] {_mcp_exc!s:.500}"
        return _classify_tool_error(result_content), False

    def _run_builtin(self, tc, turns: int) -> str:
        r = self.r
        db, workspace_id = r.db, r.workspace_id
        # Guard check for non-MCP tools (run_shell, edit, write, etc).
        # The MCP branch already guards MCP tool calls, but shell
        # commands and file edits were bypassing every hook-surface rule
        # entirely — the audit trail never saw them and no rule could
        # block, even when match_tool included "shell" or "workflow".
        # This mirrors the MCP guard check against the same rule set.
        _guard_blocked_non_mcp = False
        if r.state.get("__guard_enabled") and db and workspace_id:
            try:
                from app.modules.guard.routers.mcp import _get_rules
                import uuid as _uuid
                _guard_rules = _get_rules(db, _uuid.UUID(workspace_id))
                _tool_input_text = json.dumps(tc.input or {})
                _guard_hit = match_builtin_rule(
                    _guard_rules, tc.name, tc.input, _tool_input_text,
                )
                if _guard_hit:
                    _guard_action, _guard_msg, _guard_rule_id = self._apply_verdict(
                        tc, turns, _guard_hit, _tool_input_text,
                    )
                    if _guard_action == "block":
                        result_content = f"[guard_blocked] {_guard_msg}  [rule: {_guard_rule_id}]"
                        _guard_blocked_non_mcp = True
            except Exception as _guard_exc:
                log.warning("brain.non_mcp_dispatch.guard_failed", error=str(_guard_exc))

        # require_tests_pass guardrail: intercept commit-like calls
        # when no test run has been observed yet in this turn.
        _is_commit_call = (
            tc.name == "run_shell"
            and any(
                p in (tc.input or {}).get("command", "")
                for p in _GIT_COMMIT_PATTERNS
            )
        )
        if _guard_blocked_non_mcp:
            pass  # result_content already set to the guard block message
        elif self.require_tests_pass and _is_commit_call and not self.test_ran_this_turn:
            result_content = (
                "[guardrail_blocked] Tests must pass before committing. "
                "Run tests first."
            )
            if db and r.run_id:
                r.emit(db, r.run_id, r.block_id, "guardrail.require_tests_pass", {
                    "tool": tc.name,
                    "command": (tc.input or {}).get("command", ""),
                    "turn": turns,
                    "message": "Blocked: tests must pass before committing",
                })
        else:
            result_content = r.dispatch_with_creds(tc.name, tc.input)
            # Detect test runs so subsequent commit calls are allowed
            if (
                self.require_tests_pass
                and tc.name == "run_shell"
                and not self.test_ran_this_turn
            ):
                _cmd = (tc.input or {}).get("command", "").lower()
                if any(m in _cmd for m in _TEST_MARKERS):
                    self.test_ran_this_turn = True
        return _classify_tool_error(result_content)
