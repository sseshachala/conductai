"""Canonical OpenAI-shape ↔ Anthropic Messages shape converter (#2157).

The canonical `/gateway/v1/completions` envelope is OpenAI Chat
Completions shape by design. Anthropic-target profiles need
bidirectional translation so callers can send one envelope regardless
of what the profile actually points at.

Request side (canonical OpenAI → Anthropic):
  - ``tools[{type:"function", function:{name, description, parameters}}]``
    → ``tools:[{name, description, input_schema}]``
  - ``tool_choice: "auto" | "required"`` → ``{type:"auto"|"any"}``
  - ``tool_choice: {type:"function", function:{name}}`` → ``{type:"tool", name}``
  - ``tool_choice: "none"`` → ``{type:"none"}`` (Anthropic's explicit no-call form)
  - assistant ``tool_calls[]`` → assistant content blocks
    ``{type:"tool_use", id, name, input}`` where ``input = json.loads(arguments)``
  - ``role:"tool"`` message → user content block
    ``{type:"tool_result", tool_use_id, content}``
  - system messages → Anthropic top-level ``system`` field (extracted)

Response side (Anthropic → canonical OpenAI):
  - Anthropic ``content:[{type:"text", text}, {type:"tool_use", id, name, input}]``
    → ``choices[{message:{role:"assistant", content:<text>, tool_calls:[...]}}]``
    where ``tool_calls[].function.arguments = json.dumps(input)``.
  - Anthropic ``stop_reason: "tool_use"`` → ``finish_reason: "tool_calls"``.
  - Anthropic ``stop_reason: "end_turn"`` → ``finish_reason: "stop"``.
  - Anthropic ``usage: {input_tokens, output_tokens}`` →
    ``usage: {prompt_tokens, completion_tokens, total_tokens}``.

Redaction / validation of tool payloads still runs on the CANONICAL shape
(before request-side conversion, after response-side conversion) so the
existing rules in ``tools_validator`` don't need a per-provider variant.

Never raises on the request side unless the input violates the
canonical contract that ``tools_validator`` already enforced upstream —
if a caller reaches this converter with malformed input, it's a
programming bug in the wire-in, not a user error.

The response side treats missing fields defensively: an Anthropic
response with no ``content`` array yields ``choices[].message.content = ""``
and no ``tool_calls``, so the client still sees a valid OpenAI shape.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any


class ConverterError(Exception):
    """Non-recoverable shape error during conversion.

    Raised only when the input SHOULD have been rejected by the upstream
    validator but slipped through. Never returned to the caller as a
    normal response — this is a wire-in bug indicator.
    """

    def __init__(self, direction: str, reason: str) -> None:
        self.direction = direction  # "canonical_to_anthropic" | "anthropic_to_canonical"
        self.reason = reason
        super().__init__(f"{direction}: {reason}")


# ─── Request side: canonical OpenAI → Anthropic Messages ────────────


def canonical_to_anthropic(body: dict) -> dict:
    """Convert a canonical OpenAI-shape body to Anthropic Messages shape.

    Copies the pieces that translate cleanly (max_tokens, temperature,
    top_p, stop → stop_sequences, model, stream) and rewrites the
    parts that need shape changes (messages, system extraction, tools,
    tool_choice).

    ``model`` passes through unchanged — the caller's profile resolution
    substitutes the actual Anthropic model id at the target boundary,
    so this converter doesn't have to know about model naming.
    """
    if not isinstance(body, dict):
        raise ConverterError("canonical_to_anthropic", f"body must be dict, got {type(body).__name__}")

    result: dict[str, Any] = {}

    # Direct passthrough fields.
    for key in ("model", "max_tokens", "temperature", "top_p", "stream"):
        if key in body and body[key] is not None:
            result[key] = body[key]

    # ``stop`` → ``stop_sequences`` (Anthropic uses the plural). Accept
    # both string and list forms per the canonical schema.
    if body.get("stop") is not None:
        stops = body["stop"]
        if isinstance(stops, str):
            result["stop_sequences"] = [stops]
        elif isinstance(stops, list):
            result["stop_sequences"] = list(stops)

    # Messages: system extraction + user/assistant/tool rewrite.
    result["messages"], system_text = _rewrite_messages(body.get("messages") or [])
    if system_text:
        result["system"] = system_text

    # Tools: shape mismatch on parameters/input_schema.
    if body.get("tools"):
        result["tools"] = _rewrite_tools(body["tools"])

    # tool_choice: three-mode → Anthropic dict form. All three modes
    # produce a non-None result now (P2 #5 fix — "none" maps to
    # {"type":"none"} rather than omitting the field, which used to
    # let Anthropic default-auto-select tools the caller had disabled).
    if body.get("tool_choice") is not None:
        converted = _rewrite_tool_choice(body["tool_choice"])
        if converted is not None:
            result["tool_choice"] = converted

    return result


def _rewrite_messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Rewrite canonical messages list into Anthropic user/assistant turns.

    System messages become concatenated ``system`` text (Anthropic wants
    a single top-level system, not a role in the messages list). Multiple
    system entries join with newlines.

    ``role: "tool"`` messages become user turns containing a
    ``tool_result`` content block. Anthropic conventions bundle each
    tool_result into the user turn that would otherwise follow the
    assistant's tool_use — but for now we emit each as its own user
    turn, which Anthropic accepts.

    Returns ``(anthropic_messages, system_text)``.
    """
    out: list[dict[str, Any]] = []
    system_parts: list[str] = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")

        if role == "system":
            if isinstance(content, str):
                system_parts.append(content)
            continue

        if role == "user":
            if isinstance(content, str):
                out.append({"role": "user", "content": content})
            elif isinstance(content, list):
                # #2166 PR 2 — convert OpenAI-shape multimodal parts
                # to Anthropic shape. ``text`` parts pass through
                # unchanged; ``image_url`` parts become Anthropic
                # ``image`` blocks with either a ``base64`` source
                # (parsed from a ``data:image/*`` URL) or a ``url``
                # source (for ``https://`` URLs — Anthropic supports
                # URL image references since 2024).
                out.append({
                    "role": "user",
                    "content": _canonical_parts_to_anthropic(content),
                })
            continue

        if role == "assistant":
            tool_calls_in = msg.get("tool_calls") or []
            # Text-only assistant turn stays as plain string content
            # (Anthropic accepts both string and block-list forms; string
            # is the more common shape for text-only turns).
            if not tool_calls_in and isinstance(content, str):
                out.append({"role": "assistant", "content": content})
                continue

            blocks: list[dict[str, Any]] = []
            if isinstance(content, str) and content:
                blocks.append({"type": "text", "text": content})
            for tc in tool_calls_in:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                tc_id = tc.get("id")
                name = fn.get("name")
                args_str = fn.get("arguments") or ""
                try:
                    args_parsed = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    # tools_validator should have blocked this pre-dispatch.
                    # If we reach here, treat as empty input — safer than
                    # forwarding a string Anthropic won't accept.
                    args_parsed = {}
                if isinstance(tc_id, str) and isinstance(name, str):
                    blocks.append({
                        "type": "tool_use",
                        "id": tc_id,
                        "name": name,
                        "input": args_parsed,
                    })
            if blocks:
                out.append({"role": "assistant", "content": blocks})
            continue

        if role == "tool":
            tcid = msg.get("tool_call_id")
            if not isinstance(tcid, str) or not tcid:
                # tools_validator rejects earlier; defensive skip.
                continue
            block_content = content if isinstance(content, (str, list)) else ""
            out.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tcid,
                    "content": block_content,
                }],
            })

    return out, "\n".join(system_parts)


def _canonical_parts_to_anthropic(parts: list[Any]) -> list[dict[str, Any]]:
    """Convert an OpenAI-shape multimodal content list to Anthropic blocks.

    Vision (#2166 PR 2). Input parts are validated by
    ``vision_validator.validate_content_parts`` upstream; here we only
    need to handle the two accepted shapes:

    - ``{"type":"text","text": s}`` → passes through unchanged (both
      APIs use the same shape).
    - ``{"type":"image_url","image_url": {"url": u, "detail"?: d}}``
      →
        - For ``data:image/<subtype>;base64,<payload>`` URLs: emit
          ``{"type":"image","source":{"type":"base64","media_type":
          "image/<subtype>","data":"<payload>"}}``. Media type comes
          from the URL prefix — no re-parsing.
        - For ``https://`` URLs: emit ``{"type":"image","source":{"type":
          "url","url": u}}``. Anthropic accepts URL image sources
          natively; we do NOT server-side fetch (that'd add SSRF + latency
          + a bytes-through-our-heap channel we don't want).

    Any part that doesn't match either shape is silently dropped —
    the upstream validator would have refused it, so seeing one here
    means a caller who bypassed the validator (e.g. brain_block
    routing later), and we prefer a partial-but-safe rewrite over
    passing an OpenAI shape to Anthropic and hitting a provider 400
    with a less helpful message.
    """
    out: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype == "text":
            text = part.get("text")
            if isinstance(text, str) and text:
                out.append({"type": "text", "text": text})
            continue
        if ptype == "image_url":
            image_url = part.get("image_url") or {}
            if not isinstance(image_url, dict):
                continue
            url = image_url.get("url")
            if not isinstance(url, str) or not url:
                continue
            block = _image_url_to_anthropic_block(url)
            if block is not None:
                out.append(block)
            continue
        # Unknown part type — drop it; the shim's validator would
        # already have refused, so this is defense-in-depth.
    return out


def _image_url_to_anthropic_block(url: str) -> dict[str, Any] | None:
    """Turn one ``image_url.url`` string into an Anthropic ``image`` block.

    - ``data:image/*;base64,...``: parse the payload directly, emit
      ``{type:"base64",...}``. No network I/O.
    - ``https://...``: fetch the image server-side, base64-encode,
      emit ``{type:"base64",...}``. See ``_fetch_and_encode_image``
      for the SSRF+size guards. Chosen over ``{type:"url",...}``
      because URL-source support is inconsistent across Anthropic
      model versions / API versions / adapter layers (LiteLLM,
      Bedrock passthrough). Base64 works on every vision-capable
      Claude model since day one.

    Returns None when the URL doesn't match either accepted scheme
    or when the HTTPS fetch fails a guard (size, content-type,
    timeout). Falls back gracefully — an image that fails to fetch
    drops the part rather than crashing the whole message.
    """
    if url.startswith("data:image/") and ";base64," in url:
        prefix, payload = url.split(";base64,", 1)
        media_type = prefix[len("data:"):].split(";", 1)[0]
        if not media_type or not payload:
            return None
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": payload,
            },
        }
    if url.startswith("https://"):
        return _fetch_and_encode_image(url)
    return None


# Guards on the server-side image fetch. See ``_fetch_and_encode_image``.
_IMAGE_FETCH_TIMEOUT_SECONDS = 5.0
_IMAGE_FETCH_MAX_BYTES = 20 * 1024 * 1024  # matches data-URL cap
_IMAGE_FETCH_ALLOWED_MEDIA_PREFIX = "image/"


def _fetch_and_encode_image(url: str) -> dict[str, Any] | None:
    """Fetch an HTTPS image and return an Anthropic base64 ``image`` block.

    Guards:

    - HTTPS scheme only (caller-enforced upstream; asserted here too).
    - No HTTP redirects followed — a redirect to an internal host
      (SSRF via URL that resolves via 302) is refused. Vendor image
      hosts like picsum.photos don't need redirects for their public
      URLs; if a legitimate use case surfaces, add an allowlist of
      redirect targets rather than following blind.
    - Response Content-Type must start with ``image/`` — refuses
      HTML pages, JSON API responses, and other non-image content
      that could confuse the model or waste tokens.
    - Body capped at ``_IMAGE_FETCH_MAX_BYTES`` (20 MB, same as
      data-URL cap). Reads incrementally and aborts on cap breach.
    - Whole request bounded by ``_IMAGE_FETCH_TIMEOUT_SECONDS`` (5s).
      Anthropic's own request timeout is much longer; capping tightly
      here means a slow image never eats budget from the LLM call.

    Returns None on any guard failure so the outer converter drops
    the part instead of failing the whole message. Errors are logged
    but not raised — the caller can decide whether missing images
    warrant refusing the request (usually not; a text-only fallback
    is more useful than a hard error).
    """
    import httpx
    import base64 as _b64
    import structlog

    _log = structlog.get_logger(__name__)

    if not url.startswith("https://"):
        return None

    try:
        with httpx.Client(
            timeout=_IMAGE_FETCH_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            response = client.get(url)
            if response.status_code >= 400:
                _log.warning(
                    "vision.image_fetch.status_error",
                    url=url,
                    status=response.status_code,
                )
                return None
            content_type = (response.headers.get("content-type") or "").lower()
            media_type = content_type.split(";", 1)[0].strip()
            if not media_type.startswith(_IMAGE_FETCH_ALLOWED_MEDIA_PREFIX):
                _log.warning(
                    "vision.image_fetch.bad_content_type",
                    url=url,
                    content_type=content_type,
                )
                return None
            body = response.content
            if len(body) > _IMAGE_FETCH_MAX_BYTES:
                _log.warning(
                    "vision.image_fetch.oversize",
                    url=url,
                    size=len(body),
                    cap=_IMAGE_FETCH_MAX_BYTES,
                )
                return None
    except Exception as exc:  # noqa: BLE001 — never let a bad URL crash a request
        _log.warning(
            "vision.image_fetch.failed",
            url=url,
            err_class=type(exc).__name__,
            err=str(exc)[:200],
        )
        return None

    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": _b64.b64encode(body).decode("ascii"),
        },
    }


def _rewrite_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rewrite canonical ``tools`` list into Anthropic tool descriptors.

    Anthropic uses ``{name, description, input_schema}`` instead of
    ``{type:"function", function:{name, description, parameters}}``.
    ``input_schema`` is the same JSON Schema shape as ``parameters``.
    """
    out: list[dict[str, Any]] = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        fn = t.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            continue
        entry: dict[str, Any] = {"name": name}
        if isinstance(fn.get("description"), str):
            entry["description"] = fn["description"]
        if fn.get("parameters") is not None:
            entry["input_schema"] = fn["parameters"]
        out.append(entry)
    return out


def _rewrite_tool_choice(tool_choice: Any) -> dict[str, Any] | None:
    """Convert canonical tool_choice to Anthropic form.

    Returns None when tool_choice should be OMITTED (canonical "none",
    which has no direct Anthropic equivalent). Any other case returns
    an Anthropic dict.
    """
    if isinstance(tool_choice, str):
        if tool_choice == "auto":
            return {"type": "auto"}
        if tool_choice == "required":
            # Anthropic calls this "any" — pick ANY tool but must pick one.
            return {"type": "any"}
        if tool_choice == "none":
            # #2157 reviewer P2 #5 — omitting the choice while keeping
            # tools in the payload lets Anthropic default-auto-select.
            # Anthropic supports {"type":"none"} to forbid tool use even
            # when tools are declared; use that so the caller's "none"
            # is honoured on both providers.
            return {"type": "none"}
        raise ConverterError(
            "canonical_to_anthropic",
            f"unsupported tool_choice string mode: {tool_choice!r}",
        )
    if isinstance(tool_choice, dict):
        if tool_choice.get("type") == "function":
            fn = tool_choice.get("function") or {}
            name = fn.get("name")
            if isinstance(name, str) and name:
                return {"type": "tool", "name": name}
    raise ConverterError(
        "canonical_to_anthropic",
        f"unrecognized tool_choice: {tool_choice!r}",
    )


# ─── Response side: Anthropic Messages → canonical OpenAI ──────────


def anthropic_to_canonical(response: dict) -> dict:
    """Convert an Anthropic Messages response to OpenAI Chat Completions shape.

    Anthropic returns a top-level object with:
      - ``id``, ``model``, ``role``, ``type`` — metadata
      - ``content``: list of ``{type: "text"|"tool_use", ...}`` blocks
      - ``stop_reason``: "end_turn" | "tool_use" | "max_tokens" | "stop_sequence"
      - ``usage``: ``{input_tokens, output_tokens}``

    Canonical OpenAI expects:
      - ``id``, ``object: "chat.completion"``, ``created``, ``model``
      - ``choices[{index, message: {role, content, tool_calls?}, finish_reason}]``
      - ``usage: {prompt_tokens, completion_tokens, total_tokens}``

    Defensive on missing fields — never raises for real Anthropic
    responses. Absent ``content`` yields empty message text; absent
    ``stop_reason`` maps to ``finish_reason: "stop"``.
    """
    if not isinstance(response, dict):
        raise ConverterError(
            "anthropic_to_canonical",
            f"response must be dict, got {type(response).__name__}",
        )

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for block in response.get("content") or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            t = block.get("text")
            if isinstance(t, str):
                text_parts.append(t)
        elif btype == "tool_use":
            tc_id = block.get("id")
            name = block.get("name")
            input_dict = block.get("input")
            if not isinstance(tc_id, str) or not isinstance(name, str):
                continue
            try:
                args_str = json.dumps(input_dict if input_dict is not None else {})
            except (TypeError, ValueError):
                # Anthropic sent something un-serializable in ``input``
                # (shouldn't happen — schema-validated upstream). Drop
                # to empty rather than emit invalid JSON.
                args_str = "{}"
            tool_calls.append({
                "id": tc_id,
                "type": "function",
                "function": {"name": name, "arguments": args_str},
            })

    message: dict[str, Any] = {"role": "assistant"}
    if tool_calls:
        # Per OpenAI: when tool_calls present, content is nullable.
        message["content"] = "".join(text_parts) or None
        message["tool_calls"] = tool_calls
    else:
        message["content"] = "".join(text_parts)

    stop_reason = response.get("stop_reason")
    if stop_reason == "tool_use":
        finish_reason = "tool_calls"
    elif stop_reason == "max_tokens":
        finish_reason = "length"
    elif stop_reason == "stop_sequence":
        finish_reason = "stop"
    else:
        # "end_turn" or absent
        finish_reason = "stop"

    usage_a = response.get("usage") or {}
    usage_o: dict[str, Any] = {}
    if isinstance(usage_a, dict):
        prompt_tokens = usage_a.get("input_tokens")
        completion_tokens = usage_a.get("output_tokens")
        if isinstance(prompt_tokens, int):
            usage_o["prompt_tokens"] = prompt_tokens
        if isinstance(completion_tokens, int):
            usage_o["completion_tokens"] = completion_tokens
        if "prompt_tokens" in usage_o and "completion_tokens" in usage_o:
            usage_o["total_tokens"] = usage_o["prompt_tokens"] + usage_o["completion_tokens"]

    canonical: dict[str, Any] = {
        "id": response.get("id") or f"chatcmpl-{uuid.uuid4().hex[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": response.get("model") or "",
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": finish_reason,
        }],
    }
    if usage_o:
        canonical["usage"] = usage_o
    return canonical


__all__ = [
    "ConverterError",
    "canonical_to_anthropic",
    "anthropic_to_canonical",
]
