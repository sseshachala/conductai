"""Tool / function-calling validators + redactors for /gateway/v1/completions.

Pure library module. The shim (``completions_shim.py``) and the response
gate (``gateway_handler.py``, PR 2) both call into here so the same
contract governs both sides — no divergence, no drift.

Two kinds of failure:

- ``ValidationFailure`` — the request violates Conduct's own contract
  (unknown ``tool_choice`` mode, duplicate tool names, missing
  ``tool_call_id`` on a tool result, assistant ``content: null`` without
  ``tool_calls``, ...). The shim maps this to 400 before dispatch.

- ``RedactionFailure`` — a tool_call's ``function.arguments`` string
  isn't valid JSON, or the redactor raised while walking it. The shim
  maps this to 400 pre-dispatch; the response gate (PR 2) maps this to
  502 ``tool_arguments_validation_failed`` post-dispatch. Both are
  terminal: no auto-retry, no scrub-and-log, no silent pass-through.

We deliberately do NOT duplicate every provider rule (OpenAI's parameter
JSON Schema draft version, Anthropic's ``input_schema`` naming, etc.).
This module enforces the properties Conduct itself cares about:
identity uniqueness, structural shape, safe arguments before dispatch.
Provider-specific rejections still happen upstream and surface as normal
502s from the gateway forwarder.
"""
from __future__ import annotations

import json
from typing import Any, Iterable
from app.modules.guard.tools_redaction import (  # noqa: F401 — re-exports
    RedactionFailure, ResponseGateReason, ScanResult, _redact_string_leaves,
    redact_tool_arguments_json, redact_tool_parameters_schema, redact_tool_result_content,
    scan_response_tool_calls,
)
from app.modules.guard.tools_correlation import (  # noqa: F401 — re-exports
    _TOOL_CALL_ID_ALLOWED, _TOOL_CALL_ID_MAX_LEN, _is_header_safe_tool_call_id,
    encode_correlation_header, extract_tool_names_supplied, extract_tool_results_supplied,
    extract_tools_offered, generate_tool_call_correlation_ids, parse_correlation_header,
)


class ValidationFailure(Exception):
    """Contract violation — malformed request that we refuse before dispatch.

    ``field`` is a dotted path pointing at the offending piece of the
    request so the shim can build a targeted 400 message instead of
    quoting the whole body back at the caller.
    """

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


# ─── tool_choice validation ─────────────────────────────────────────

# Modes Conduct's shim accepts. Anything else — including nulls,
# integers, or unknown string constants — is refused with a targeted
# error message so callers see the exact reason.
_TOOL_CHOICE_STRING_MODES = frozenset({"auto", "none", "required"})


def validate_tool_choice(
    tool_choice: Any,
    tools: list[dict[str, Any]] | None,
) -> None:
    """Enforce the ``tool_choice`` contract.

    Nothing to enforce when ``tool_choice`` is absent (None). The
    presence of ``tools`` alone doesn't make ``tool_choice`` required;
    OpenAI defaults to ``"auto"`` in that case, which is what we want.

    When the caller sent ``tool_choice``:
      - string form must be one of ``auto`` / ``none`` / ``required``;
      - dict form must be ``{"type":"function", "function":{"name": str}}``
        and the named function MUST appear in ``tools[].function.name``.

    Raises ``ValidationFailure`` on any deviation. Never mutates.
    """
    if tool_choice is None:
        return

    if isinstance(tool_choice, str):
        if tool_choice not in _TOOL_CHOICE_STRING_MODES:
            raise ValidationFailure(
                "tool_choice",
                f"unsupported mode {tool_choice!r} — allowed: "
                f"{sorted(_TOOL_CHOICE_STRING_MODES)!r}",
            )
        return

    if not isinstance(tool_choice, dict):
        raise ValidationFailure(
            "tool_choice",
            f"must be a string (auto|none|required) or an object "
            f"{{type:function, function:{{name:...}}}}, got "
            f"{type(tool_choice).__name__}",
        )

    if tool_choice.get("type") != "function":
        raise ValidationFailure(
            "tool_choice.type",
            f"only ``function`` supported, got {tool_choice.get('type')!r}",
        )

    fn = tool_choice.get("function")
    if not isinstance(fn, dict):
        raise ValidationFailure(
            "tool_choice.function",
            "must be an object {name: str}",
        )
    name = fn.get("name")
    if not isinstance(name, str) or not name:
        raise ValidationFailure(
            "tool_choice.function.name",
            "must be a non-empty string",
        )

    declared_names = _declared_tool_names(tools or [])
    if name not in declared_names:
        raise ValidationFailure(
            "tool_choice.function.name",
            f"named choice {name!r} does not appear in ``tools[].function.name`` "
            f"(declared: {sorted(declared_names)!r})",
        )


def _declared_tool_names(tools: Iterable[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for t in tools:
        if not isinstance(t, dict):
            continue
        fn = t.get("function")
        if isinstance(fn, dict):
            n = fn.get("name")
            if isinstance(n, str):
                names.add(n)
    return names


# ─── tools list validation ──────────────────────────────────────────


def validate_tools(tools: Any) -> None:
    """Enforce the ``tools`` contract.

    - Must be a non-empty list when present (an empty list is a
      contract mistake, not a real "no tools" signal — omit the field).
    - Each entry is ``{"type":"function", "function":{"name":..., ...}}``.
    - Tool names within a single request must be unique. Duplicate names
      would let a caller shadow a legitimate tool with a same-named
      malicious one; ``tool_choice`` name resolution would then pick
      whichever hit first in the client's iteration order.
    """
    if not isinstance(tools, list):
        raise ValidationFailure(
            "tools", f"must be a list, got {type(tools).__name__}",
        )
    if not tools:
        raise ValidationFailure("tools", "must contain at least one entry when present")

    seen: set[str] = set()
    for i, entry in enumerate(tools):
        if not isinstance(entry, dict):
            raise ValidationFailure(
                f"tools[{i}]", f"must be an object, got {type(entry).__name__}",
            )
        if entry.get("type") != "function":
            raise ValidationFailure(
                f"tools[{i}].type",
                f"only ``function`` supported, got {entry.get('type')!r}",
            )
        fn = entry.get("function")
        if not isinstance(fn, dict):
            raise ValidationFailure(
                f"tools[{i}].function", "must be an object with at least ``name``",
            )
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            raise ValidationFailure(
                f"tools[{i}].function.name", "must be a non-empty string",
            )
        if name in seen:
            raise ValidationFailure(
                f"tools[{i}].function.name",
                f"duplicate tool name {name!r} within request "
                "(names must be unique so tool_choice resolution is unambiguous)",
            )
        seen.add(name)


# ─── message structure validation ───────────────────────────────────


def validate_messages(messages: list[dict[str, Any]]) -> None:
    """Enforce tool-related structural rules on messages.

    Per-role invariants:
      - ``role: "tool"`` — MUST carry a non-empty ``tool_call_id``
        string. Without it the server can't correlate the result back
        to the tool call that asked for it; upstream will 400 anyway
        but we want to surface a targeted error, not a generic upstream
        rejection.
      - ``role: "assistant"`` — ``content: null`` is allowed only when
        ``tool_calls`` is a non-empty list. Otherwise it's a caller
        mistake (empty assistant turn) that upstream would reject with
        a less useful message.
      - Assistant ``tool_calls[]`` entries MUST have ``id`` (non-empty
        string), ``type: "function"``, and ``function.name`` (non-empty
        string). ``function.arguments`` MUST be a string (JSON-encoded
        per OpenAI contract — even if the caller sent it as a dict, the
        provider wire format is a string).
    """
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise ValidationFailure(
                f"messages[{i}]", f"must be an object, got {type(msg).__name__}",
            )
        role = msg.get("role")
        if role in ("user", "system"):
            content = msg.get("content")
            # #2166 PR 1 — accept list content (multimodal parts) in
            # addition to plain strings. Deep validation of parts
            # (URL scheme allowlist, size caps, image count) lives in
            # ``vision_validator.validate_content_parts`` so this
            # module doesn't have to know about image_url shape.
            if isinstance(content, str):
                if content == "":
                    raise ValidationFailure(
                        f"messages[{i}].content",
                        f"``role: {role}`` messages require a non-empty string content",
                    )
            elif isinstance(content, list):
                if not content:
                    raise ValidationFailure(
                        f"messages[{i}].content",
                        f"``role: {role}`` messages require at least one content part",
                    )
            else:
                raise ValidationFailure(
                    f"messages[{i}].content",
                    f"``role: {role}`` messages require string or list content, "
                    f"got {type(content).__name__}",
                )
        elif role == "tool":
            tcid = msg.get("tool_call_id")
            if not isinstance(tcid, str) or not tcid:
                raise ValidationFailure(
                    f"messages[{i}].tool_call_id",
                    "``role: tool`` messages must carry a non-empty "
                    "tool_call_id correlating back to the assistant's tool_call",
                )
        elif role == "assistant":
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")
            if content is None and not (isinstance(tool_calls, list) and tool_calls):
                raise ValidationFailure(
                    f"messages[{i}].content",
                    "assistant ``content: null`` only allowed when tool_calls "
                    "is a non-empty list",
                )
            if tool_calls is not None:
                _validate_assistant_tool_calls(tool_calls, path=f"messages[{i}].tool_calls")


def _validate_assistant_tool_calls(tool_calls: Any, *, path: str) -> None:
    if not isinstance(tool_calls, list):
        raise ValidationFailure(
            path, f"must be a list, got {type(tool_calls).__name__}",
        )
    for i, tc in enumerate(tool_calls):
        p = f"{path}[{i}]"
        if not isinstance(tc, dict):
            raise ValidationFailure(p, f"must be an object, got {type(tc).__name__}")
        if not isinstance(tc.get("id"), str) or not tc["id"]:
            raise ValidationFailure(f"{p}.id", "must be a non-empty string")
        if tc.get("type") != "function":
            raise ValidationFailure(
                f"{p}.type",
                f"only ``function`` supported, got {tc.get('type')!r}",
            )
        fn = tc.get("function")
        if not isinstance(fn, dict):
            raise ValidationFailure(f"{p}.function", "must be an object")
        if not isinstance(fn.get("name"), str) or not fn["name"]:
            raise ValidationFailure(f"{p}.function.name", "must be a non-empty string")
        # arguments is a JSON-encoded STRING on the wire (OpenAI contract).
        # If the caller sent a dict, we don't silently accept it — the wire
        # format is a string and a dict here means the caller wrote a
        # non-portable shape that upstream will reject inconsistently.
        args = fn.get("arguments")
        if args is not None and not isinstance(args, str):
            raise ValidationFailure(
                f"{p}.function.arguments",
                "must be a JSON-encoded string per OpenAI contract, got "
                f"{type(args).__name__}",
            )


# ─── token estimation ──────────────────────────────────────────────


def estimate_tools_tokens(tools: Any) -> int:
    """Conservative pre-dispatch estimate for tool-schema token cost.

    Provider-accurate cost is settled at ``finalize`` from real
    ``usage``; this exists so ``reserve_budgets_for_request`` doesn't
    under-bill by omitting the tool definitions from the reservation.
    Under-reserving means customers exceed their budget by the
    tool-schema overhead every time — silent regression on #2154's
    reservation hardening.

    Approach: ``len(json.dumps(tools)) // 4``. Over-estimates on
    average (OpenAI's actual tokenizer is denser than 4 chars per
    token for JSON), which is the safe direction for pre-dispatch
    reservations. No tokenizer swap — that's a separate epic.

    Absent / empty / non-serializable inputs return 0; the caller then
    contributes nothing extra, matching today's behavior on requests
    with no ``tools`` field.
    """
    if not tools:
        return 0
    try:
        return len(json.dumps(tools, ensure_ascii=False)) // 4
    except (TypeError, ValueError):
        # Non-JSON-serializable input shouldn't get here — validator
        # rejects earlier — but if it does, better to skip the estimate
        # than crash the entire pre-dispatch path.
        return 0


__all__ = [
    "ValidationFailure",
    "RedactionFailure",
    "validate_tool_choice",
    "validate_tools",
    "validate_messages",
    "redact_tool_arguments_json",
    "redact_tool_parameters_schema",
    "redact_tool_result_content",
    "estimate_tools_tokens",
    "scan_response_tool_calls",
    "extract_tools_offered",
    "extract_tool_results_supplied",
    "extract_tool_names_supplied",
    "generate_tool_call_correlation_ids",
    "encode_correlation_header",
    "parse_correlation_header",
    "ResponseGateReason",
    "ScanResult",
]
