"""Tool-call correlation IDs (response header encode/parse) and audit extraction of offered/supplied tools.

Re-exported from ``tools_validator``."""

from __future__ import annotations



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


def parse_correlation_header(header_value: str | None) -> dict[str, str]:
    """Inverse of ``encode_correlation_header`` — parses the wire format.

    Callers (conduct-cli, litellm-guard shim, brain_block routing) read
    ``response.headers["X-Conduct-Tool-Correlation-Ids"]`` and pass it
    here to get back a ``{tool_call_id: correlation_id}`` mapping they
    can attach to their own execution log / Flight Recorder entry.

    Malformed pairs are dropped silently — the header is best-effort
    metadata, never load-bearing. Missing header, empty string, and
    ``None`` all return an empty dict.
    """
    if not header_value:
        return {}
    out: dict[str, str] = {}
    for pair in header_value.split(","):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k or not v:
            continue
        if not _is_header_safe_tool_call_id(k):
            continue
        out.setdefault(k, v)
    return out


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
