"""#2155 — Streaming + tools with buffered-delta validation.

Pure module. Wraps an SSE byte-stream from an OpenAI-shape completion
so ``tool_calls[].function.arguments`` fragments are held back across
deltas, validated + redacted once assembled, and emitted only if they
pass the same response-gate contract as non-streaming (``tools_validator``
+ the composed engine that runs afterward).

Text ``delta.content`` chunks stream through unchanged — TTFB for
text is preserved. TTFB for tool-heavy responses effectively equals
total generation time; that's the cost of enforcing the invariant
"zero raw unsafe bytes reach the client" and it applies to
non-streaming too.

Why a pure module (no FastAPI imports):

- Reused by the gateway handler wire-in AND by unit tests that feed
  raw SSE bytes without spinning up a request.
- Failure paths (parse errors, redactor raises, malformed frames)
  degrade to a synthetic SSE error frame + [DONE]. The client's SDK
  raises the same shape as any other tool-arguments failure.
- Correlation IDs from #2158 are stamped after the buffered gate,
  same helper as non-streaming — no divergence.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import AsyncIterator

# SSE frame boundary — spec allows LF or CRLF; upstream OpenAI uses \n\n.
# Callers on other providers pass their bytes through litellm_sdk which
# normalises to the OpenAI shape before this wrapper sees anything, so
# ``\n\n`` is the only separator we need to split on.
_SSE_SEP = b"\n\n"
_SSE_DATA_PREFIX = b"data: "
_SSE_DONE = b"[DONE]"


@dataclass
class _ToolCallBuf:
    """Per-tool-call state accumulated across streaming deltas.

    ``args_parts`` is a list (not a string) so we don't pay a quadratic
    cost concatenating tokens on every delta — one ``"".join`` at flush
    time is O(n) in total length. ``id`` and ``name`` land on the first
    delta; subsequent deltas only carry ``arguments`` fragments.
    """

    index: int
    id: str = ""
    type: str = "function"
    name: str = ""
    args_parts: list[str] = field(default_factory=list)

    def add_args(self, fragment: str) -> None:
        if fragment:
            self.args_parts.append(fragment)

    def assembled_arguments(self) -> str:
        return "".join(self.args_parts)


@dataclass
class _ChoiceState:
    """Per-choice buffer state.

    A single response can have multiple choices (``n>1``); each choice
    has its own tool_calls sequence indexed independently. Real-world
    calls almost always have ``n=1`` but the wrapper handles ``n>1``
    correctly — the buffer key is (choice_index, tool_call_index).
    """

    tool_calls: dict[int, _ToolCallBuf] = field(default_factory=dict)
    finished: bool = False
    finish_reason: str | None = None
    _first_chunk_seen: bool = False
    _first_chunk_meta: dict = field(default_factory=dict)


def _parse_sse_frame(frame: bytes) -> dict | None:
    """Parse one SSE event's ``data:`` line into a JSON dict.

    Returns None for keep-alive comments (lines starting with ``:``),
    the ``[DONE]`` sentinel, or malformed frames (never raises). The
    caller distinguishes ``[DONE]`` via ``is_done_frame(frame)`` which
    is cheap; this parser stays pure JSON-or-None.

    Multi-line ``data:`` blocks (SSE spec allows several ``data:``
    lines to concatenate before the blank line) are joined with ``\\n``
    per the spec. In practice OpenAI emits one ``data:`` per event.
    """
    lines = frame.split(b"\n")
    payload_lines: list[bytes] = []
    for line in lines:
        line = line.rstrip(b"\r")
        if not line or line.startswith(b":"):
            continue
        if line.startswith(_SSE_DATA_PREFIX):
            payload_lines.append(line[len(_SSE_DATA_PREFIX):])
        # ignore other SSE fields (event:, id:, retry:) — completion
        # streams don't use them.
    if not payload_lines:
        return None
    payload = b"\n".join(payload_lines).strip()
    if not payload or payload == _SSE_DONE:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def is_done_frame(frame: bytes) -> bool:
    """True iff the frame is the SSE terminator ``data: [DONE]``.

    Split out so callers can drop or re-emit the marker without
    re-parsing. Keep-alive comments are NOT done frames.
    """
    for line in frame.split(b"\n"):
        line = line.strip().rstrip(b"\r")
        if line.startswith(_SSE_DATA_PREFIX):
            payload = line[len(_SSE_DATA_PREFIX):].strip()
            if payload == _SSE_DONE:
                return True
    return False


def _extract_tool_deltas(chunk: dict) -> list[tuple[int, list[dict]]]:
    """Pull ``(choice_index, tool_call_deltas)`` pairs from one chunk.

    Returns an empty list when no choice in the chunk carries a
    ``delta.tool_calls`` field. Text-only deltas produce ``[]`` so the
    caller treats them as passthrough.
    """
    out: list[tuple[int, list[dict]]] = []
    for choice in chunk.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        idx = choice.get("index", 0)
        if not isinstance(idx, int):
            continue
        delta = choice.get("delta") or {}
        tcs = delta.get("tool_calls")
        if isinstance(tcs, list) and tcs:
            out.append((idx, tcs))
    return out


def _apply_tool_delta(buf: _ToolCallBuf, delta: dict) -> None:
    """Merge one delta piece into the accumulating tool_call buffer.

    OpenAI's stream sends ``id`` + ``type`` + ``function.name`` on the
    first fragment; every subsequent fragment for the same index carries
    only ``function.arguments``. We accept them landing on any fragment
    so a non-OpenAI provider that emits them later still works.
    """
    if not isinstance(delta, dict):
        return
    if "id" in delta and isinstance(delta["id"], str) and delta["id"]:
        buf.id = delta["id"]
    if "type" in delta and isinstance(delta["type"], str):
        buf.type = delta["type"]
    fn = delta.get("function") or {}
    if isinstance(fn, dict):
        if "name" in fn and isinstance(fn["name"], str) and fn["name"]:
            buf.name = fn["name"]
        if "arguments" in fn and isinstance(fn["arguments"], str):
            buf.add_args(fn["arguments"])


def _finish_reason_for_choice(chunk: dict, target_idx: int) -> str | None:
    """Return ``finish_reason`` for the given choice index in this chunk.

    None when the chunk doesn't carry a finish for this choice.
    """
    for choice in chunk.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        if choice.get("index", 0) != target_idx:
            continue
        fr = choice.get("finish_reason")
        if isinstance(fr, str) and fr:
            return fr
    return None


def _synthesize_tool_calls_frame(
    state: _ChoiceState,
    choice_index: int,
) -> bytes:
    """Emit one SSE frame carrying the fully-assembled, redacted tool_calls.

    The frame shape mirrors what OpenAI SDKs expect at end-of-stream:
    a single delta with ``tool_calls`` populated. Reusing ``delta``
    (not ``message``) means SDKs that accumulate incrementally still
    concatenate correctly; sending ``message`` would leave a duplicate
    since earlier fragments already used ``delta.tool_calls``.
    """
    tool_calls_out = []
    for idx, buf in sorted(state.tool_calls.items()):
        tool_calls_out.append({
            "index": idx,
            "id": buf.id,
            "type": buf.type,
            "function": {
                "name": buf.name,
                "arguments": buf.assembled_arguments(),
            },
        })
    payload = {
        # id / created / model land on the first upstream chunk; we don't
        # need to echo them here because the SDK has already accumulated
        # the envelope. The delta-only shape is a valid mid-stream chunk.
        "choices": [{
            "index": choice_index,
            "delta": {"tool_calls": tool_calls_out},
            "finish_reason": None,
        }],
    }
    return _SSE_DATA_PREFIX + json.dumps(payload).encode("utf-8") + _SSE_SEP


def _synthesize_error_frame(reason: str, source: str) -> bytes:
    """Emit one SSE frame carrying a terminal ``conduct_gateway_tool_arguments_validation_failed`` error.

    Shape matches the non-streaming 502 body from ``apply_tool_call_gate``
    so a client using the same error-handling code path recognises it.
    We deliberately do NOT emit a ``choices[]`` array on this frame —
    the client sees the error and stops accumulating.
    """
    payload = {
        "error": {
            "type": "conduct_gateway_tool_arguments_validation_failed",
            "message": (
                "Tool_call arguments failed validation and cannot be "
                "safely delivered. Upstream inference completed and is "
                "billed; the tool call is refused."
            ),
            "detail": reason,
            "source": source,
            "gate": "response-stream",
        }
    }
    return _SSE_DATA_PREFIX + json.dumps(payload).encode("utf-8") + _SSE_SEP


def _validate_buffered_tool_calls(
    state: _ChoiceState,
) -> tuple[bool, str | None, str | None]:
    """Run the same validator + redactor used on the non-streaming path.

    Returns ``(ok, reason, source)``. On success the state has been
    mutated in place — each ``args_parts`` is replaced by a single
    redacted string. On failure the state is untouched and the caller
    emits an error frame.

    Kept inline (not delegating to ``scan_response_tool_calls``) because
    the non-streaming scanner expects a full ``choices[].message`` shape
    while streaming state is keyed by tool_call.index. Same rules,
    smaller adapter surface.
    """
    from app.modules.guard.tools_validator import (
        RedactionFailure,
        redact_tool_arguments_json,
    )

    redacted: dict[int, str] = {}
    for idx, buf in state.tool_calls.items():
        try:
            safe_str, _found = redact_tool_arguments_json(
                buf.assembled_arguments(),
                source="response-stream",
            )
            redacted[idx] = safe_str
        except RedactionFailure as exc:
            return False, exc.reason, exc.source
        except Exception as exc:  # noqa: BLE001
            return False, f"unexpected: {type(exc).__name__}", "response-stream"
    for idx, safe in redacted.items():
        state.tool_calls[idx].args_parts = [safe]
    return True, None, None


async def wrap_tool_stream(
    upstream: AsyncIterator[bytes],
) -> AsyncIterator[bytes]:
    """Wrap an OpenAI-shape SSE stream that MAY carry tool_calls.

    Contract:

    - Text-only ``delta.content`` frames pass through unchanged, in
      order, immediately. No TTFB penalty for text.
    - Frames carrying ``delta.tool_calls`` are BUFFERED (not yielded).
      The wrapper accumulates each call's ``function.arguments``
      fragments per choice index.
    - When ``finish_reason == "tool_calls"`` arrives, the wrapper runs
      the validator + redactor on the assembled arguments. On success it
      emits ONE synthetic frame containing all the completed
      ``tool_calls`` for that choice, then re-emits the finish frame
      unchanged. On failure it emits ONE synthetic error frame and
      re-emits the finish frame with ``finish_reason: "error"``.
    - Any other ``finish_reason`` (``stop``, ``length``, ``content_filter``)
      flushes any partial buffer as a "premature finish" error and passes
      the finish frame through — a tool_call started but never closed is
      a contract violation upstream and we refuse to guess.
    - The terminal ``data: [DONE]`` frame is always re-emitted last.

    Yielded chunks include the ``\\n\\n`` frame separator; callers pipe
    them straight to a ``StreamingResponse`` body_iterator without
    re-framing.
    """
    buffer = b""
    # One state per choice index. Almost always {0: ...} but handles n>1.
    choices: dict[int, _ChoiceState] = {}

    async for chunk in upstream:
        # Normalise: some upstream libraries yield str, most yield bytes.
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        buffer += chunk

        # Emit every complete frame we can from the accumulator. A frame
        # is a run of non-empty lines terminated by a blank line — we
        # split on ``\n\n`` and re-attach the separator on emit so any
        # frame we pass through keeps its exact wire form.
        while _SSE_SEP in buffer:
            frame, buffer = buffer.split(_SSE_SEP, 1)
            async for out in _handle_frame(frame, choices):
                yield out

    # End-of-stream: flush any leftover buffered frame (rare — most
    # upstreams end cleanly on ``\n\n``). If a partial frame ends the
    # stream, we drop it silently rather than emit half-json.
    #
    # Terminal safety net: if we buffered tool_calls but never saw a
    # finish_reason (upstream disconnect mid-tool_call), refuse the
    # tool_call with an error frame + synthetic [DONE].
    for choice_index, state in choices.items():
        if state.finished or not state.tool_calls:
            continue
        yield _synthesize_error_frame(
            "stream ended before finish_reason for tool_calls",
            "response-stream",
        )
        break
    yield _SSE_DATA_PREFIX + _SSE_DONE + _SSE_SEP


async def _handle_frame(
    frame: bytes,
    choices: dict[int, _ChoiceState],
) -> AsyncIterator[bytes]:
    """Route one parsed SSE frame — passthrough, buffer, or flush.

    Split out from ``wrap_tool_stream`` so the buffering / flushing
    decisions can be unit-tested against fixed frame lists without
    setting up an async iterator.
    """
    # Preserve the terminal [DONE] frame: swallow it here, the caller's
    # end-of-stream path re-emits so we don't double up. We DO consume
    # it (not passthrough) so any inbound [DONE] doesn't come out
    # before our flush frames.
    if is_done_frame(frame):
        return

    parsed = _parse_sse_frame(frame)
    if parsed is None:
        # Comment, keep-alive, or unparseable frame. Pass through — a
        # comment upstream deserves to be visible downstream (SDKs
        # ignore comments; ops tooling may not).
        yield frame + _SSE_SEP
        return

    deltas = _extract_tool_deltas(parsed)

    # ── passthrough: text delta or non-tool frame ────────────────────
    if not deltas:
        # Still check for finish_reason on any choice — a stream can end
        # with a bare finish frame (no delta). Flush the buffer before
        # emitting the finish so tool_calls land in order.
        async for out in _flush_finish_choices(parsed, choices):
            yield out
        yield frame + _SSE_SEP
        return

    # ── tool_calls delta: buffer, do NOT yield the raw frame ─────────
    for choice_idx, tool_deltas in deltas:
        state = choices.setdefault(choice_idx, _ChoiceState())
        for tc_delta in tool_deltas:
            if not isinstance(tc_delta, dict):
                continue
            tc_index = tc_delta.get("index", 0)
            if not isinstance(tc_index, int):
                continue
            buf = state.tool_calls.setdefault(tc_index, _ToolCallBuf(index=tc_index))
            _apply_tool_delta(buf, tc_delta)

    # A single chunk can carry BOTH tool_call deltas AND a finish frame
    # (rare but valid). Handle the finish after buffering so the flushed
    # tool_calls include the fragments that arrived in the same chunk.
    async for out in _flush_finish_choices(parsed, choices):
        yield out


async def _flush_finish_choices(
    parsed: dict,
    choices: dict[int, _ChoiceState],
) -> AsyncIterator[bytes]:
    """Emit flush frames for any choice hitting a finish_reason in this chunk.

    - ``finish_reason == "tool_calls"``: run validator + redactor on the
      buffer, emit synthetic tool_calls frame OR error frame.
    - Other finish reasons: if a tool_call was mid-flight, emit an error
      frame (premature finish is a contract violation).
    - No finish for a choice: nothing to flush yet.

    Does NOT re-emit the caller's finish frame — that's the caller's job.
    """
    for choice_idx, state in list(choices.items()):
        fr = _finish_reason_for_choice(parsed, choice_idx)
        if fr is None:
            continue
        if state.finished:
            continue
        state.finished = True
        state.finish_reason = fr

        if not state.tool_calls:
            continue

        if fr != "tool_calls":
            yield _synthesize_error_frame(
                f"finish_reason={fr!r} while tool_call buffer was open",
                "response-stream",
            )
            continue

        ok, reason, source = _validate_buffered_tool_calls(state)
        if not ok:
            yield _synthesize_error_frame(reason or "unknown", source or "response-stream")
            continue

        yield _synthesize_tool_calls_frame(state, choice_idx)
