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

from app.core.pii import redact_pii, redact_secrets


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


class RedactionFailure(Exception):
    """Redaction refused to complete safely.

    Either the payload didn't parse as JSON (``json_parse``), the
    redactor mutated a non-string in a way that can't round-trip
    (``non_string_leaf``), or an unexpected structure surfaced
    (``structure``). The caller decides the HTTP code (400 pre-dispatch,
    502 post-dispatch — both terminal, per the epic).
    """

    def __init__(self, reason: str, *, source: str) -> None:
        self.reason = reason
        # ``source`` names WHERE the failure happened so audit + logs can
        # distinguish "tool argument on the request path" from "tool
        # argument on the response path" without stringifying context.
        self.source = source
        super().__init__(f"{source}: {reason}")


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
            if not isinstance(content, str) or content == "":
                raise ValidationFailure(
                    f"messages[{i}].content",
                    f"``role: {role}`` messages require a non-empty string content",
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


# ─── redaction — parse, walk, re-serialize ──────────────────────────


def _redact_string_leaves(node: Any, *, source: str) -> tuple[Any, list[str]]:
    """Walk a parsed-JSON tree, redacting string leaves in place.

    Keys are preserved. Non-string leaves (int, float, bool, None) are
    preserved untouched — the reviewer's guidance: "Preserve argument
    keys and non-string types." Only string values are candidates for
    redaction, which is where credential + PII regexes actually match.

    Returns ``(new_tree, found_labels)``. Never raises unless the tree
    contains unhashable structures we can't walk — that path is treated
    as ``RedactionFailure(reason="structure", source=source)`` at the
    caller level so the request is refused instead of half-redacted.
    """
    found: list[str] = []

    def _walk(x: Any) -> Any:
        if isinstance(x, str):
            scrubbed = redact_pii(x)
            if scrubbed != x:
                found.append("pii")
            cleaned, secrets = redact_secrets(scrubbed)
            found.extend(secrets)
            return cleaned
        if isinstance(x, dict):
            return {k: _walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [_walk(v) for v in x]
        # int / float / bool / None — untouched.
        return x

    try:
        return _walk(node), found
    except Exception as exc:  # noqa: BLE001
        raise RedactionFailure(f"walk raised {type(exc).__name__}", source=source) from exc


def redact_tool_arguments_json(arguments: str, *, source: str) -> tuple[str, list[str]]:
    """Redact a tool_call ``function.arguments`` JSON string.

    Parses, walks string leaves, re-serializes. On JSON parse failure
    or walk failure, raises ``RedactionFailure`` — the caller MUST NOT
    swallow this and forward the original string. That's the
    "block, don't scrub" rule from the epic.

    ``arguments`` is expected to be a JSON-encoded string per OpenAI's
    wire contract. Non-string input is a caller mistake caught earlier
    in ``validate_messages``; if it slips through we still refuse.
    """
    if not isinstance(arguments, str):
        raise RedactionFailure(
            f"expected JSON-encoded string, got {type(arguments).__name__}",
            source=source,
        )
    if not arguments:
        # Empty arguments string is a legal "no-arg tool call" shape and
        # nothing to redact. Return as-is with no findings.
        return arguments, []
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise RedactionFailure(
            f"arguments not valid JSON: {exc.msg} at pos {exc.pos}",
            source=source,
        ) from exc
    walked, found = _redact_string_leaves(parsed, source=source)
    try:
        redacted = json.dumps(walked, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise RedactionFailure(
            f"redacted tree not JSON-serializable: {type(exc).__name__}",
            source=source,
        ) from exc
    return redacted, found


def redact_tool_parameters_schema(parameters: Any, *, source: str) -> tuple[Any, list[str]]:
    """Redact a tool's ``function.parameters`` JSON Schema.

    The schema is already a dict/list tree (not a JSON-encoded string
    like ``arguments``). Walks + returns a new tree; raises
    ``RedactionFailure`` if the structure isn't walkable. String leaves
    inside descriptions, enums, examples, etc. are all candidates —
    a customer could paste a secret into a tool description accidentally.
    """
    if parameters is None:
        return parameters, []
    return _redact_string_leaves(parameters, source=source)


def redact_tool_result_content(content: str) -> tuple[str, list[str]]:
    """Redact ``role: "tool"`` message content.

    Tool result content is a plain string (per OpenAI contract). Scan
    it directly — no JSON parse — same rules as any other message text.
    Non-string input is caller error; validator catches it upstream so
    this helper doesn't need a fallback path.
    """
    if not isinstance(content, str):
        raise RedactionFailure(
            f"tool-result content must be string, got {type(content).__name__}",
            source="tool_result_content",
        )
    if not content:
        return content, []
    found: list[str] = []
    scrubbed = redact_pii(content)
    if scrubbed != content:
        found.append("pii")
    cleaned, secrets = redact_secrets(scrubbed)
    found.extend(secrets)
    return cleaned, found


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



# ─── response-gate helpers (PR 2 of #2159) ─────────────────────────


class ResponseGateReason:
    """String constants for the audit ``routing_meta.response_gate_reason``.

    Kept as attributes on a stable class (not an Enum) so JSON
    serialization is trivial and downstream string comparisons in
    Flight Recorder + audit UIs don't need import glue.
    """

    POLICY_BLOCK = "policy_block"
    VALIDATION_FAILURE = "validation_failure"


class ScanResult:
    """Return type of ``scan_response_tool_calls``.

    ``scanned_body`` is the deep-copied response with ``arguments``
    strings replaced by their redacted equivalents. ``generated_calls``
    is the audit-friendly list of ``{name, id}`` for
    ``routing_meta.tool_calls_generated``. ``error`` is populated ONLY
    on redaction failure; the caller MUST refuse the response when
    error is set (block, don't scrub).
    """

    __slots__ = ("scanned_body", "generated_calls", "error")

    def __init__(
        self,
        scanned_body: dict | None,
        generated_calls: list[dict[str, str]],
        error: RedactionFailure | None,
    ) -> None:
        self.scanned_body = scanned_body
        self.generated_calls = generated_calls
        self.error = error


def scan_response_tool_calls(response_body: dict) -> ScanResult:
    """Walk OpenAI-shape response body, redact tool_call arguments.

    Extracts + validates every ``choices[].message.tool_calls[]`` entry:

      1. Records ``{name, id}`` for audit.
      2. Parses ``function.arguments`` as JSON.
      3. Walks string leaves through the existing PII + secret scrubbers.
      4. Re-serializes and writes back into the body.

    On JSON parse failure or walk failure at any tool_call, returns a
    ``ScanResult`` with ``error`` set and ``scanned_body=None``. The
    caller MUST convert that to a 502 ``tool_arguments_validation_failed``
    response envelope — see epic #2159 for the reasoning
    (blocking is safer than scrubbing to a placeholder because an
    executor might still act on it, apply defaults, or retry
    unpredictably).

    Non-tool responses (no ``choices[].message.tool_calls``) return
    the body unchanged with an empty generated_calls list and no error.
    """
    import copy as _copy

    if not isinstance(response_body, dict):
        return ScanResult(scanned_body=response_body, generated_calls=[], error=None)

    choices = response_body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ScanResult(scanned_body=response_body, generated_calls=[], error=None)

    generated: list[dict[str, str]] = []
    any_tool_call = False

    # Detect FIRST — deep-copy only when we actually need to mutate.
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        msg = choice.get("message")
        if not isinstance(msg, dict):
            continue
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            any_tool_call = True
            break

    if not any_tool_call:
        return ScanResult(scanned_body=response_body, generated_calls=[], error=None)

    scanned = _copy.deepcopy(response_body)
    for i, choice in enumerate(scanned.get("choices") or []):
        if not isinstance(choice, dict):
            continue
        msg = choice.get("message")
        if not isinstance(msg, dict):
            continue
        tool_calls = msg.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for j, tc in enumerate(tool_calls):
            if not isinstance(tc, dict):
                continue
            tc_id = tc.get("id") if isinstance(tc.get("id"), str) else ""
            fn = tc.get("function")
            fn_name = ""
            if isinstance(fn, dict):
                if isinstance(fn.get("name"), str):
                    fn_name = fn["name"]
                # #2159 PR 2 reviewer P1 #1 — arguments MUST be a
                # JSON-encoded string per OpenAI wire contract. Objects,
                # nulls, or missing values slip through if we only
                # inspect nonempty strings; block those the same way
                # we block malformed JSON (terminal 502 upstream).
                if "arguments" in fn:
                    args = fn.get("arguments")
                    if not isinstance(args, str):
                        return ScanResult(
                            scanned_body=None, generated_calls=[],
                            error=RedactionFailure(
                                (
                                    "arguments must be a JSON-encoded string per "
                                    f"OpenAI contract, got {type(args).__name__}"
                                ),
                                source=(
                                    f"choices[{i}].message.tool_calls[{j}]"
                                    ".function.arguments"
                                ),
                            ),
                        )
                    if args:
                        try:
                            redacted, _found = redact_tool_arguments_json(
                                args,
                                source=(
                                    f"choices[{i}].message.tool_calls[{j}]"
                                    ".function.arguments"
                                ),
                            )
                            fn["arguments"] = redacted
                        except RedactionFailure as exc:
                            return ScanResult(
                                scanned_body=None, generated_calls=[], error=exc,
                            )
            generated.append({"name": fn_name, "id": tc_id})
    return ScanResult(scanned_body=scanned, generated_calls=generated, error=None)


# Whitelist of characters allowed in a tool_call.id we're willing to
# echo back in the correlation response header. ASCII-only, no
# delimiters, bounded length. Model-controlled IDs that violate the
# whitelist are dropped from the header (the correlation still lives
# in routing_meta for audit-side lookup — we just can't safely emit
# it on the wire).
_TOOL_CALL_ID_MAX_LEN = 128
_TOOL_CALL_ID_ALLOWED = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "_-.:"
)


def _is_header_safe_tool_call_id(tcid: str) -> bool:
    """True when tcid can be safely echoed in a comma/equals-delimited header.

    Rejects: non-ASCII (UnicodeEncodeError on the wire), commas + equals
    (ambiguates the mapping), any char not in the whitelist, and any
    string longer than ``_TOOL_CALL_ID_MAX_LEN`` (bounded emission).
    """
    if not tcid or len(tcid) > _TOOL_CALL_ID_MAX_LEN:
        return False
    return all(ch in _TOOL_CALL_ID_ALLOWED for ch in tcid)


def generate_tool_call_correlation_ids(
    generated_calls: list[dict[str, str]],
) -> dict[str, str]:
    """#2158 — assign a stable correlation id per generated tool_call.

    Returns a mapping of ``tool_call_id → correlation_id`` where each
    correlation_id is a fresh 16-hex UUID slice. The runtime executor
    reads the ``X-Conduct-Tool-Correlation-Ids`` response header and
    attaches the correlation to its own Flight Recorder entry so both
    sides can be joined: gateway audit row X (``tool_call.generated``)
    ↔ executor entry Y (``tool_call.completed``).

    Uses uuid4 not the tool_call.id itself so:
      - the identifier is not model-controlled (LLMs choose call_id;
        we never want Flight Recorder correlation to be steerable by
        the model);
      - the same tool_call re-tried across audit rows lands with
        distinct correlations (each attempt is its own event).

    Reviewer P2 #4 (2026-09-20): tool_call.id is model-controlled and
    may contain commas, equals, or non-ASCII characters that break the
    header encoding. Duplicate IDs also produce an ambiguous mapping.
    This function only records the FIRST occurrence of any id and only
    emits ids in the returned dict — the caller (``encode_correlation
    _header``) applies the header-safety filter separately.

    Empty input returns an empty mapping.
    """
    import uuid as _uuid

    out: dict[str, str] = {}
    for call in generated_calls or []:
        if not isinstance(call, dict):
            continue
        tcid = call.get("id")
        if not isinstance(tcid, str) or not tcid:
            continue
        if tcid in out:
            # Duplicate IDs from the model would silently overwrite;
            # keep the first correlation so downstream can join by the
            # value that was actually emitted.
            continue
        out[tcid] = _uuid.uuid4().hex[:16]
    return out


def encode_correlation_header(correlation_ids: dict[str, str]) -> str:
    """Encode ``{tool_call_id: correlation_id}`` for the response header.

    Format: ``call_1=corr_hex1,call_2=corr_hex2`` — one line, comma
    separated. Empty map returns empty string; caller must skip
    setting the header when the string is empty (many HTTP servers
    drop headers with empty values, and an empty header is misleading).

    Reviewer P2 #4 (2026-09-20): silently drops tool_call.ids that
    fail ``_is_header_safe_tool_call_id`` — model-controlled inputs
    can contain commas, equals, or non-ASCII characters that would
    either ambiguate the mapping or crash the response gate with
    UnicodeEncodeError. The correlation for a dropped id remains in
    ``routing_meta.tool_call_correlation_ids`` for audit-side lookup,
    only the wire echo is suppressed.
    """
    if not correlation_ids:
        return ""
    safe = [
        f"{k}={v}" for k, v in correlation_ids.items()
        if _is_header_safe_tool_call_id(k)
    ]
    return ",".join(safe)


def extract_tools_offered(request_body: dict) -> list[str]:
    """Names from ``request.tools[].function.name`` for audit.

    Read-only; returns empty list when the request has no tools or the
    structure is malformed. Never raises — audit rows should land even
    when the request shape is off-spec.
    """
    tools = request_body.get("tools") if isinstance(request_body, dict) else None
    if not isinstance(tools, list):
        return []
    names: list[str] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        fn = t.get("function")
        if isinstance(fn, dict) and isinstance(fn.get("name"), str):
            names.append(fn["name"])
    return names


def extract_tool_results_supplied(request_body: dict) -> list[str]:
    """``tool_call_id`` values from ``role: "tool"`` messages.

    Reviewer P2 #3 (2026-09-20): these are IDENTIFIERS, not tool
    names. Kept as its own extractor because audit rows want the
    correlation-id trail (which supplied results correlate to which
    prior tool_calls), and rules that key on ID (rare but real) work
    off this list. Rules that key on NAMES must use the separate
    ``extract_tool_names_supplied`` below — the two signals are not
    interchangeable, and the earlier version conflated them by
    exposing IDs under the ``names`` label.

    Distinct from ``tool_calls_generated`` (what the model returned
    THIS turn) per the epic's "gateway sees generation, not
    execution" language.
    """
    messages = request_body.get("messages") if isinstance(request_body, dict) else None
    if not isinstance(messages, list):
        return []
    ids: list[str] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "tool":
            tcid = m.get("tool_call_id")
            if isinstance(tcid, str) and tcid:
                ids.append(tcid)
    return ids


def extract_tool_names_supplied(request_body: dict) -> list[str]:
    """Tool NAMES corresponding to ``role: "tool"`` results in this request.

    Reviewer P2 #3 (2026-09-20): resolves each tool result's
    ``tool_call_id`` back to the tool NAME from the preceding
    assistant's ``tool_calls[]``. Rules like
    ``match_tool_name_supplied: bank_transfer`` need this list — the
    previous implementation gave them raw IDs (e.g. ``call_abc``) and
    the rule never matched.

    Walk order: build a lookup ``{tool_call_id → name}`` from every
    assistant turn's ``tool_calls``, then walk the messages and emit
    each supplied result's resolved name (skipping any ID that has no
    matching assistant declaration — that indicates a malformed
    transcript that would fail upstream anyway).

    Never raises; returns [] on malformed input.
    """
    messages = request_body.get("messages") if isinstance(request_body, dict) else None
    if not isinstance(messages, list):
        return []
    lookup: dict[str, str] = {}
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            tcid = tc.get("id")
            fn = tc.get("function") or {}
            name = fn.get("name") if isinstance(fn, dict) else None
            if isinstance(tcid, str) and tcid and isinstance(name, str) and name:
                # First declaration wins if the transcript accidentally
                # duplicates an id — matches how the correlation helper
                # handles duplicates.
                lookup.setdefault(tcid, name)
    names: list[str] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "tool":
            tcid = m.get("tool_call_id")
            if isinstance(tcid, str) and tcid and tcid in lookup:
                names.append(lookup[tcid])
    return names

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
    "ResponseGateReason",
    "ScanResult",
]
