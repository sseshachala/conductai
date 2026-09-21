"""#2166 PR 1 — vision (image_url) validation for /gateway/v1/completions.

Pure module. Enforces Conduct's contract for multimodal ``image_url``
content parts before the request reaches the executor:

- URL scheme allowlist (``https://`` and ``data:image/*`` only).
  ``http://`` is refused for SSRF + unencrypted-transfer reasons;
  ``file://`` is refused so a caller can't exfiltrate arbitrary
  files from the gateway host; anything else (``ftp://``, ``s3://``,
  bare paths, ...) is a caller mistake at the boundary.

- Per-message image count cap (default 20) matching OpenAI's own
  contract so we return the same-shape error at the same time OpenAI
  would rather than the caller learning about it 300ms later from
  upstream.

- Per-data-URL size cap (default 20MB decoded) so a caller can't
  wedge the vault + audit path by shipping a 500MB base64 blob.

The response gate side of vision (scanning image content for PII
after the model returns) is a SEPARATE epic requiring OCR + face
detection — explicitly out of scope for PR 1. This module only
touches REQUEST validation.

Text parts of a multimodal message (``{"type":"text","text":...}``)
are already walked by ``_redact_body`` in ``gateway_helpers.py``
(the request-path redactor walks list-shaped ``message.content``
and scrubs each ``block["text"]``), so multimodal doesn't create
a redaction hole. No extra wiring needed on the shim side.
"""
from __future__ import annotations

import base64
from typing import Any


# OpenAI's own documented limits at time of writing (2026-09-20).
# Kept as constants so an admin can override via a settings-facing
# knob later without hunting for magic numbers.
MAX_IMAGES_PER_MESSAGE = 20
MAX_DATA_URL_DECODED_BYTES = 20 * 1024 * 1024  # 20MB
_DATA_URL_PREFIX = "data:image/"


class VisionValidationFailure(Exception):
    """Contract violation on a vision content part.

    ``field`` is a dotted path pointing at the offending piece of the
    request so the shim can build a targeted 400 message instead of
    quoting the whole body back at the caller.
    """

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"{field}: {reason}")


def validate_content_parts(
    parts: list[Any],
    *,
    message_index: int,
) -> None:
    """Enforce the multimodal-content contract on one message's parts.

    Accepts a list of ``{"type":"text","text":...}`` or
    ``{"type":"image_url","image_url":{"url":..., "detail"?:...}}``
    dicts. Anything else is a contract violation.

    Never mutates. Raises ``VisionValidationFailure`` on the first
    problem — one bad part refuses the whole message, same shape as
    ``tools_validator`` does with tool_calls.

    Text parts pass through unchanged (redaction happens downstream
    in ``_redact_body`` which already walks list-shaped content).
    """
    if not isinstance(parts, list):
        raise VisionValidationFailure(
            f"messages[{message_index}].content",
            f"must be a string or a list of content parts, "
            f"got {type(parts).__name__}",
        )
    if not parts:
        # Empty list is a contract mistake — a message with no parts
        # tells the model nothing. Callers who mean "no message"
        # should omit the message.
        raise VisionValidationFailure(
            f"messages[{message_index}].content",
            "content list must contain at least one part",
        )

    image_count = 0
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            raise VisionValidationFailure(
                f"messages[{message_index}].content[{i}]",
                f"each part must be an object, got {type(part).__name__}",
            )
        ptype = part.get("type")
        if ptype == "text":
            _validate_text_part(part, message_index, i)
        elif ptype == "image_url":
            _validate_image_part(part, message_index, i)
            image_count += 1
            if image_count > MAX_IMAGES_PER_MESSAGE:
                raise VisionValidationFailure(
                    f"messages[{message_index}].content",
                    f"too many images in one message "
                    f"(max {MAX_IMAGES_PER_MESSAGE})",
                )
        else:
            raise VisionValidationFailure(
                f"messages[{message_index}].content[{i}].type",
                f"unsupported part type {ptype!r} — "
                f"allowed: 'text' | 'image_url'",
            )


def _validate_text_part(
    part: dict[str, Any],
    message_index: int,
    part_index: int,
) -> None:
    text = part.get("text")
    if not isinstance(text, str):
        raise VisionValidationFailure(
            f"messages[{message_index}].content[{part_index}].text",
            f"must be a string, got {type(text).__name__}",
        )
    # No length cap here — the top-level canonical validator already
    # caps total message content length. Enforcing it again on a
    # per-part basis would double-count and give a misleading error.


def _validate_image_part(
    part: dict[str, Any],
    message_index: int,
    part_index: int,
) -> None:
    """Enforce the image_url shape: {"image_url": {"url": str, "detail"?: str}}.

    OpenAI's shape lets ``image_url`` be either a bare string OR an
    object; we require the object form for parity with the tools
    validator (structural clarity + room for the ``detail`` field
    without special-casing the string branch).
    """
    image_url = part.get("image_url")
    if not isinstance(image_url, dict):
        raise VisionValidationFailure(
            f"messages[{message_index}].content[{part_index}].image_url",
            f"must be an object {{url: str, detail?: str}}, "
            f"got {type(image_url).__name__}",
        )
    url = image_url.get("url")
    if not isinstance(url, str) or not url:
        raise VisionValidationFailure(
            f"messages[{message_index}].content[{part_index}].image_url.url",
            "must be a non-empty string",
        )

    # Scheme allowlist. https:// is allowed unconditionally; data URLs
    # are allowed only for the image/* subset (data:application/pdf...
    # is a document, not an image, and the model will reject it — refuse
    # at the boundary with a clear error). Everything else is refused.
    if url.startswith(_DATA_URL_PREFIX):
        _validate_data_url(url, message_index, part_index)
    elif url.startswith("https://"):
        # Length sanity check — an HTTPS URL longer than 2KB is almost
        # certainly a corrupted paste or a malformed data URL. Bounded
        # to avoid pathological inputs downstream.
        if len(url) > 2048:
            raise VisionValidationFailure(
                f"messages[{message_index}].content[{part_index}].image_url.url",
                f"https URL too long (max 2048 chars, got {len(url)})",
            )
    else:
        raise VisionValidationFailure(
            f"messages[{message_index}].content[{part_index}].image_url.url",
            f"unsupported URL scheme — allowed: 'https://', 'data:image/*'. "
            f"Refused: http, file, ftp, s3, bare paths, and anything else. "
            f"SSRF + unencrypted-transfer risks are why http is not allowed.",
        )

    detail = image_url.get("detail")
    if detail is not None and detail not in ("auto", "low", "high"):
        raise VisionValidationFailure(
            f"messages[{message_index}].content[{part_index}].image_url.detail",
            f"must be one of 'auto' | 'low' | 'high', got {detail!r}",
        )


def _validate_data_url(url: str, message_index: int, part_index: int) -> None:
    """Enforce data URL size cap + shape.

    Format: ``data:image/<subtype>[;charset=...];base64,<payload>``.
    Non-base64 data URLs (``data:image/png,<raw>``) are also legal per
    RFC 2397 but nobody uses them for images — we accept only the
    base64 form so the size math is deterministic (URL length ≈ 4/3 of
    decoded size), which lets us reject oversize BEFORE decoding.
    """
    if ";base64," not in url:
        raise VisionValidationFailure(
            f"messages[{message_index}].content[{part_index}].image_url.url",
            "data URL must be base64-encoded (data:image/*;base64,...)",
        )
    prefix, payload = url.split(";base64,", 1)
    # Cheap upper-bound check: base64 encoding inflates by ~4/3.
    # If ``len(payload) * 3 / 4`` already exceeds the cap, refuse
    # without paying the decode cost.
    approx_decoded = (len(payload) * 3) // 4
    if approx_decoded > MAX_DATA_URL_DECODED_BYTES:
        raise VisionValidationFailure(
            f"messages[{message_index}].content[{part_index}].image_url.url",
            f"data URL too large "
            f"(approx {approx_decoded} decoded bytes, "
            f"max {MAX_DATA_URL_DECODED_BYTES})",
        )
    # Best-effort base64 sanity check — a malformed payload here
    # would land as a 400 from upstream anyway; catching it locally
    # gives the caller a targeted error instead.
    try:
        base64.b64decode(payload, validate=True)
    except (ValueError, TypeError) as exc:
        raise VisionValidationFailure(
            f"messages[{message_index}].content[{part_index}].image_url.url",
            f"data URL payload is not valid base64: {type(exc).__name__}",
        ) from exc


def count_images(content: Any) -> int:
    """Return the number of image_url parts in a multimodal message.

    Used by the token estimator to add per-image token budget to the
    pre-dispatch reservation. Returns 0 for plain string content or
    lists with no images.
    """
    if not isinstance(content, list):
        return 0
    return sum(
        1
        for p in content
        if isinstance(p, dict) and p.get("type") == "image_url"
    )


# #2166 PR 2 — conservative per-image token estimate.
#
# OpenAI's own docs put image cost between ~85 tokens (``detail=low``)
# and ~765 tokens (``detail=high``, tiled 512x512 patches). Anthropic
# lands in a similar range. We conservatively bill 1000 tokens/image
# so the pre-dispatch budget reservation over-counts rather than
# under-bills. Final settlement happens post-response using real
# ``usage`` from the provider (same path as tools_tokens), so this
# only affects the reservation cap check, never the final invoice.
#
# Rationale for a single constant vs per-detail-level math: the
# ``detail`` field is optional and the provider may re-detail images
# without telling us, so the reservation stays conservative. Ops can
# tune this if a workspace routinely runs into cap denials on
# vision-heavy traffic (mostly rare — text tokens dominate cost).
_TOKENS_PER_IMAGE = 1000


def estimate_vision_tokens(body: dict) -> int:
    """Return a conservative total-image-token estimate for a request body.

    Walks ``body["messages"][].content`` (list-shaped only), counts
    image_url parts, multiplies by ``_TOKENS_PER_IMAGE``. Returns 0
    for a request with no images. Never raises — an unexpected shape
    falls back to 0 so the pre-dispatch reservation never blows up
    on a malformed body (the shim's validator refuses those anyway,
    this is defense-in-depth).
    """
    try:
        total_images = 0
        for msg in body.get("messages") or []:
            if not isinstance(msg, dict):
                continue
            total_images += count_images(msg.get("content"))
        return total_images * _TOKENS_PER_IMAGE
    except Exception:
        return 0


__all__ = [
    "VisionValidationFailure",
    "validate_content_parts",
    "count_images",
    "estimate_vision_tokens",
    "MAX_IMAGES_PER_MESSAGE",
    "MAX_DATA_URL_DECODED_BYTES",
]
