"""Tool-calling redactors and the response-gate scan for /gateway/v1/completions.

``RedactionFailure`` is terminal on both sides: the shim maps it to 400
pre-dispatch, the response gate to 502 post-dispatch. Re-exported from
``tools_validator``, which documents the full contract."""

from __future__ import annotations

import json
from typing import Any
from app.core.pii import redact_pii, redact_secrets


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

    native_calls = [item for key in ("content", "output") for item in (response_body.get(key) or [])
                    if isinstance(item, dict) and item.get("type") in
                    {"tool_use", "server_tool_use", "function_call", "custom_tool_call"}]
    if native_calls:
        scanned = _copy.deepcopy(response_body)
        generated = []
        for key in ("content", "output"):
            for item in (scanned.get(key) or []):
                if not isinstance(item, dict) or item.get("type") not in {
                    "tool_use", "server_tool_use", "function_call", "custom_tool_call",
                }:
                    continue
                kind = item["type"]
                try:
                    if kind in {"tool_use", "server_tool_use"}:
                        if not isinstance(item.get("input"), dict):
                            raise RedactionFailure("tool input must be an object", source=key)
                        safe, _ = redact_tool_arguments_json(json.dumps(item["input"]), source=key)
                        item["input"] = json.loads(safe)
                    elif kind == "function_call":
                        safe, _ = redact_tool_arguments_json(item.get("arguments"), source=key)
                        item["arguments"] = safe
                    else:
                        if not isinstance(item.get("input"), str):
                            raise RedactionFailure("custom tool input must be a string", source=key)
                        item["input"], _ = redact_tool_result_content(item["input"])
                except Exception as exc:
                    failure = exc if isinstance(exc, RedactionFailure) else RedactionFailure(
                        "invalid native tool arguments", source=key,
                    )
                    return ScanResult(scanned_body=None, generated_calls=[], error=failure)
                generated.append({"name": item.get("name", ""), "id": item.get("call_id") or item.get("id", "")})
        return ScanResult(scanned_body=scanned, generated_calls=generated, error=None)

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
