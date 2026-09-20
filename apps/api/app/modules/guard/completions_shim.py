"""Profile-native ``POST /gateway/v1/completions`` shim (#2144).

Adapter over the existing Gateway v2 executor. The canonical request the
shim accepts is OpenAI Chat Completions shape with ``profile`` in place of
``model``:

    {
      "profile":  "cond-<8chars>-<alias>",
      "messages": [{"role": "user", "content": "..."}],
      "max_tokens": 128,
      "temperature": 0.7
    }

The shim validates the canonical body with strict field/type checks, rewrites
``profile`` → ``model`` (which the v2 executor's cond_code parser already
understands), and delegates to ``handle_gateway_request`` with the OpenAI
operation. In PR 1 only profiles that ``accepts`` the
``openai_chat_completions`` operation are supported; Anthropic-target
profiles land in a follow-up with a canonical → Anthropic Messages converter
and a response normalizer back to canonical shape.

Streaming (``stream: true``) forwards upstream SSE bytes verbatim through the
same v2 executor path used by the SDK-shaped OpenAI route — no separate code
path here; the response is whatever ``handle_gateway_request`` produces
(``StreamingResponse`` for stream=true, ``JSONResponse`` otherwise).

Validation rules — every one of these is a hard fail with 400 BEFORE any
delegation happens. Silent fall-through to legacy routing is the class of
bug this file exists to prevent.

- ``profile`` MUST match ``cond-<8chars>-<alias>`` exactly. Anything else
  is rejected here so it cannot slip past the executor's parser and land
  on the v1 code path.
- ``stream`` MUST be a strict JSON boolean. Non-bools like ``1`` /
  ``"true"`` / ``"no"`` are rejected — the reviewer's P2 fix from PR 1
  stays intact via ``StrictBool``. When true, the response is
  ``text/event-stream`` (OpenAI-shape SSE) that the caller iterates
  chunk-by-chunk; when false or omitted the response is a single JSON body.
- ``messages[].content`` MUST be a plain string. No multimodal blocks
  (image/audio) yet — those are follow-up PRs.
- No ``tools`` / ``functions`` / ``response_format`` / etc. — the strict
  schema (``extra="forbid"``) rejects any field not on the allowlist.

ponytail: single small module for now. Split into request/response
sub-modules only if PR 2/3 pushes this file past 500 LOC.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    ValidationError,
    field_validator,
)

from app.guard.router import fail_closed as _fail_closed
from app.modules.guard.gateway_handler import (
    _extract_cond_code,
    handle_gateway_request,
)


def _reject(status: int, message: str) -> JSONResponse:
    """Return the shared gateway-shaped rejection envelope.

    ``_fail_closed`` builds a ``JSONResponse`` in the same error shape the
    SDK-shaped routes emit for pre-execution refusals. It does NOT write
    an audit row — audited rejections belong to the v2 executor's own
    lifecycle (policy block, budget refusal, admission refusal), which
    runs strictly downstream of this shim. Pre-delegation validation
    failures here are intentionally not audited: the request never
    reached the point where a governed attempt could be recorded, and
    logging every unauth'd 400 would flood the audit stream with noise
    that carries no security signal.
    """
    return _fail_closed(status, message)


class _CanonicalMessage(BaseModel):
    """One turn in the canonical envelope. Text content only in PR 1."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=0, max_length=1_000_000)


class _CanonicalRequest(BaseModel):
    """Strict canonical request. ``extra="forbid"`` rejects any unknown
    field (``tools``, ``functions``, ``response_format``, ``seed``,
    ``logprobs``, ...) so the promised "no tools / no vision / text
    only" contract is a schema fact, not a code review reminder.
    """

    model_config = ConfigDict(extra="forbid")

    profile: str
    messages: list[_CanonicalMessage] = Field(min_length=1, max_length=1_000)
    max_tokens: int = Field(gt=0, le=100_000)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    stop: list[str] | str | None = None
    # StrictBool means only the JSON literals ``true`` / ``false`` are
    # accepted. ``stream: 1`` / ``"false"`` / ``"no"`` all trip validation
    # here, not later inside the executor's ``bool(...)`` coercion — the
    # reviewer P2 fix from PR 1 stays intact even though this field now
    # accepts True (previously locked to False by ``Literal[False]``).
    stream: StrictBool = False
    # Same trick for the alias — an "unknown" field would be forbidden
    # by ``extra="forbid"``, but making ``model`` an explicitly-typed
    # ``None``-only field gives the client a targeted error message
    # instead of a generic "extra fields forbidden" complaint.
    model: None = Field(
        default=None,
        description=(
            "Not allowed on /gateway/v1/completions — send `profile` "
            "instead. The profile picks the model server-side."
        ),
    )

    @field_validator("profile")
    @classmethod
    def _profile_must_be_valid_cond_id(cls, value: str) -> str:
        """Reject anything that isn't ``cond-<8chars>-<alias>``.

        The executor uses ``_extract_cond_code`` to decide whether v2
        handles a request or it falls through to legacy v1 routing. If
        the shim let ``profile: "gpt-4o"`` through, the executor's
        parser would return ``None`` and the request would silently
        route via v1 — the exact bypass this shim exists to prevent.
        Reusing the executor's parser here means one regex governs both
        sides with zero drift risk.
        """
        cond_code = _extract_cond_code(value)
        if cond_code is None:
            raise ValueError(
                "`profile` must match the format cond-<8chars>-<alias> "
                "(lowercase alphanumeric code, e.g. cond-abcd1234-gpt-4o)"
            )
        return value


async def gateway_completions_impl(
    request: Request,
    background: BackgroundTasks,
) -> StreamingResponse | JSONResponse:
    """Handle ``POST /gateway/v1/completions``.

    OpenAI-target profiles only (Anthropic-target support lands in a
    follow-up). Body is validated by the strict canonical schema, then
    ``profile`` is rewritten to ``model`` so the v2 executor's existing
    cond_code parser can pick the profile. No other conversion is needed
    because the canonical envelope IS the OpenAI Chat Completions shape.

    Return type is ``StreamingResponse`` when ``stream=true`` (forwards
    upstream SSE bytes verbatim), otherwise ``JSONResponse``. Both cases
    flow through the same v2 executor entry so admission / policy /
    budget / audit are identical.
    """
    try:
        raw = await request.json()
    except Exception:
        return _reject(400, "Body must be valid JSON")
    if not isinstance(raw, dict):
        return _reject(400, "Body must be a JSON object")

    if raw.get("model") is not None:
        # Targeted message so the caller understands why the field is
        # rejected, instead of Pydantic's generic "input should be null".
        return _reject(
            400,
            "`model` is not allowed on /gateway/v1/completions — send "
            "`profile` instead. The profile picks the model server-side.",
        )

    try:
        canonical = _CanonicalRequest.model_validate(raw)
    except ValidationError as exc:
        return _reject(400, _format_validation_error(exc))

    provider_body = _canonical_to_openai_body(canonical)

    # ponytail: mutate starlette's Request body cache in place — the
    # handler reads via ``await request.json()`` / ``await request.body()``
    # which both honour ``_body`` / ``_json`` when already set. Upgrade
    # to a proper ``Request(scope, receive)`` wrapper if we ever need to
    # rewrite headers or the URL too.
    provider_bytes = json.dumps(provider_body).encode()
    request._body = provider_bytes  # type: ignore[attr-defined]
    request._json = provider_body  # type: ignore[attr-defined]

    return await handle_gateway_request(
        request,
        background,
        provider="openai",
        upstream_path="/v1/chat/completions",
        auth_header_in="authorization",
        auth_header_out="authorization",
        bearer=True,
        canonical_profile=True,
    )


def _canonical_to_openai_body(canonical: _CanonicalRequest) -> dict[str, Any]:
    """Rewrite ``profile`` → ``model``; drop schema-only fields.

    The canonical envelope IS OpenAI Chat Completions shape by design, so
    PR 1's OpenAI-only path needs no field conversion. When PR 2 adds
    Anthropic-target support it will branch here to build an Anthropic
    Messages body instead (extract system → top-level, etc).
    """
    body: dict[str, Any] = {
        "model": canonical.profile,
        "messages": [msg.model_dump() for msg in canonical.messages],
        "max_tokens": canonical.max_tokens,
        # Pass ``stream`` through verbatim. The downstream v2 executor
        # (handle_gateway_request -> _execute_v2 with stream=True) returns
        # a StreamingResponse whose body iterator forwards the upstream
        # SSE bytes; we return that response unchanged so /completions
        # streams in the same OpenAI Chat Completions SSE format.
        "stream": canonical.stream,
    }
    if canonical.stream:
        # Reviewer P1 (streaming PR): OpenAI's streaming responses omit
        # the ``usage`` block by default; the final usage chunk is only
        # emitted when the client sends ``stream_options.include_usage=true``
        # (https://help.openai.com/en/articles/10478918). Without it,
        # ``_extract_token_counts`` returns (None, None) so audit rows
        # and budget settlement carry zero tokens for successful streams.
        # Injected server-side rather than exposed to the canonical
        # request schema — /completions callers should not need to know
        # about wire-level accounting knobs, and Conduct owns the audit
        # trail regardless of what the caller wants.
        body["stream_options"] = {"include_usage": True}
    if canonical.temperature is not None:
        body["temperature"] = canonical.temperature
    if canonical.top_p is not None:
        body["top_p"] = canonical.top_p
    if canonical.stop is not None:
        body["stop"] = canonical.stop
    return body


def _format_validation_error(exc: ValidationError) -> str:
    """Turn a Pydantic ValidationError into a single-line 400 message.

    First error only — the shim is a validation boundary, not a form. A
    caller that fixes one field will re-send and see the next error if
    any remains. Keeps the 400 body compact enough to log-grep on.
    """
    err = exc.errors()[0]
    loc = ".".join(str(part) for part in err.get("loc", ())) or "body"
    msg = err.get("msg", "validation error")
    return f"{loc}: {msg}"


__all__ = ["gateway_completions_impl"]
