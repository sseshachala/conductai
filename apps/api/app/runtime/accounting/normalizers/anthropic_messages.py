"""Anthropic Messages usage normalizer.

Handles both JSON and SSE. Streaming usage arrives across two events:

- ``message_start`` — usage.input_tokens, cache_creation_input_tokens,
  cache_read_input_tokens (and optionally the tiered ``cache_creation`` dict
  when 1h cache is enabled).
- ``message_delta`` — usage.output_tokens (final).

Interrupted streams: ``message_start`` seen but no terminal ``message_delta``
→ PARTIAL completeness. No usage at all → UNAVAILABLE.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from app.runtime.accounting.contracts import (
    TokenBreakdown,
    UsageCompleteness,
    UsageOrigin,
)
from app.runtime.accounting.normalizers.base import (
    NORMALIZER_VERSION,
    NormalizedUsage,
    ProviderFamily,
    unavailable_result,
)
from app.runtime.accounting.normalizers.sse import SSEParser

_FAMILY = ProviderFamily.ANTHROPIC_MESSAGES


def _extract_cache_write_by_tier(usage: Mapping[str, Any]) -> dict[str, int]:
    """Handle both flat and per-tier cache_creation reporting.

    Newer Anthropic API returns a ``cache_creation`` dict with
    ``ephemeral_5m_input_tokens`` and ``ephemeral_1h_input_tokens`` per tier.
    Older responses report a flat ``cache_creation_input_tokens`` scalar,
    which we bucket under the default 5-minute tier.
    """
    tiered = usage.get("cache_creation")
    if isinstance(tiered, dict):
        out: dict[str, int] = {}
        for key, val in tiered.items():
            if not isinstance(val, (int, float)) or val < 0:
                continue
            if key.endswith("_input_tokens"):
                tier = key[: -len("_input_tokens")]
            else:
                tier = key
            out[tier] = int(val)
        if out:
            return out
    scalar = usage.get("cache_creation_input_tokens")
    if isinstance(scalar, (int, float)) and scalar > 0:
        return {"ephemeral_5m": int(scalar)}
    return {}


def _tokens_from_usage(usage: Mapping[str, Any]) -> TokenBreakdown:
    """Anthropic ``input_tokens`` DOES NOT include cache reads — they are a
    separate bucket. So total_input = input + cache_read + cache_write.

    Reviewer #8 (#2221): distinguishes "no usage fields present" (all None)
    from "reported zero" (explicit 0). All-None → TokenBreakdown with every
    field None; the ``.normalize_*`` methods surface UNAVAILABLE from that.
    """
    input_only = usage.get("input_tokens")
    cache_read = usage.get("cache_read_input_tokens")
    cache_write_by_tier = _extract_cache_write_by_tier(usage)
    output = usage.get("output_tokens")

    input_is_numeric = isinstance(input_only, (int, float))
    cache_read_is_numeric = isinstance(cache_read, (int, float))
    output_is_numeric = isinstance(output, (int, float))
    any_field_reported = (
        input_is_numeric
        or cache_read_is_numeric
        or output_is_numeric
        or bool(cache_write_by_tier)
    )

    if not any_field_reported:
        # No usage fields present at all — do NOT synthesize zeros.
        return TokenBreakdown()

    cache_write_total = sum(cache_write_by_tier.values())
    parts: list[int] = []
    if input_is_numeric:
        parts.append(int(input_only))
    if cache_read_is_numeric:
        parts.append(int(cache_read))
    if cache_write_total or cache_write_by_tier:
        parts.append(cache_write_total)
    total_input = sum(parts) if parts else None

    return TokenBreakdown(
        total_input_tokens=total_input,
        total_output_tokens=int(output) if output_is_numeric else None,
        uncached_input_tokens=int(input_only) if input_is_numeric else None,
        cache_read_tokens=int(cache_read) if cache_read_is_numeric else None,
        cache_write_tokens_by_tier=cache_write_by_tier,
    )


def _merge_usage(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """message_delta only carries output_tokens; overlay it onto message_start."""
    merged = dict(base)
    for key, val in overlay.items():
        if val is None:
            continue
        merged[key] = val
    return merged


class AnthropicMessagesNormalizer:
    family = _FAMILY
    version = NORMALIZER_VERSION

    def normalize_json(self, payload: bytes | str | dict) -> NormalizedUsage:
        obj: Any
        if isinstance(payload, (bytes, str)):
            try:
                obj = json.loads(payload)
            except (ValueError, TypeError):
                return _unavailable()
        else:
            obj = payload
        if not isinstance(obj, dict):
            return _unavailable()
        usage = obj.get("usage")
        if not isinstance(usage, dict) or not usage:
            return _unavailable()
        tokens = _tokens_from_usage(usage)
        # Reviewer #8 (#2221): an empty usage dict OR one that produces no
        # numeric fields must surface UNAVAILABLE, not COMPLETE-with-zero.
        if (
            tokens.total_output_tokens is None
            and tokens.total_input_tokens is None
            and tokens.cache_read_tokens is None
            and not tokens.cache_write_tokens_by_tier
        ):
            return _unavailable()
        origin = UsageOrigin.PROVIDER_REPORTED
        completeness = UsageCompleteness.COMPLETE
        return NormalizedUsage(
            tokens=tokens,
            origin=origin,
            completeness=completeness,
            provider_family=_FAMILY,
            raw_usage=dict(usage),
        )

    def normalize_sse(self, payload: bytes) -> NormalizedUsage:
        parser = SSEParser()
        start_usage: dict[str, Any] = {}
        delta_usage: dict[str, Any] = {}
        saw_terminal = False

        def _handle(event_name: str, data: str) -> None:
            nonlocal start_usage, delta_usage, saw_terminal
            try:
                payload = json.loads(data)
            except ValueError:
                return
            if not isinstance(payload, dict):
                return
            evt_type = payload.get("type") or event_name
            if evt_type == "message_start":
                msg = payload.get("message") or {}
                usage = msg.get("usage")
                if isinstance(usage, dict):
                    start_usage = dict(usage)
            elif evt_type == "message_delta":
                usage = payload.get("usage")
                if isinstance(usage, dict):
                    delta_usage.update(usage)
            elif evt_type == "message_stop":
                saw_terminal = True

        for evt in parser.feed(payload):
            _handle(evt.event, evt.data)
        for evt in parser.flush():
            _handle(evt.event, evt.data)

        if not start_usage and not delta_usage:
            return _unavailable()

        merged = _merge_usage(start_usage, delta_usage)
        tokens = _tokens_from_usage(merged)

        if saw_terminal and (
            tokens.total_output_tokens is not None or tokens.total_input_tokens is not None
        ):
            completeness = UsageCompleteness.COMPLETE
        elif start_usage and not delta_usage:
            completeness = UsageCompleteness.PARTIAL
        else:
            completeness = UsageCompleteness.COMPLETE

        return NormalizedUsage(
            tokens=tokens,
            origin=UsageOrigin.NORMALIZED_STREAM,
            completeness=completeness,
            provider_family=_FAMILY,
            raw_usage=merged,
        )


def _unavailable() -> NormalizedUsage:
    return unavailable_result(_FAMILY)
