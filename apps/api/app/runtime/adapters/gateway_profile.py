"""Gateway profile LLMClient — canonical /gateway/v1/completions (#2170 PR 2).

Speaks the profile-native envelope: ``{profile, messages, tools, max_tokens, ...}``.
Same protocol as ``OpenAIClient`` / ``AnthropicClient`` so brain_block just swaps
the constructor when a workflow has ``gateway_profile_id`` pinned. Underneath,
the Gateway resolves the profile → picks a target (OpenAI native, Anthropic
native, LiteLLM SDK, passthrough) → executes → returns an OpenAI Chat
Completions-shaped response.

Non-streaming only in this PR. Streaming lands in the follow-up — SSE
reassembly of ``delta.tool_calls[].function.arguments`` requires the same
buffered-delta contract the shim wraps upstream today, and shipping that
here doubles the diff without unlocking a customer feature. Callers that
need streaming keep using the direct-provider adapters until then.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Iterator

from app.runtime.llm_client import (
    LLMResponse,
    LLMTextBlock,
    LLMToolUseBlock,
    LLMUsage,
    post_with_retry,
    raise_if_guard_proxy_blocked,
)
from app.runtime.pricing import get_model_rates


def _infer_provider_from_model(model: str) -> str | None:
    """Best-effort provider guess from the OpenAI-shape response ``model`` field.

    Canonical responses always echo the upstream model. Cost tables key on
    (provider, model), so we need a provider slug. Prefix heuristics cover
    every model in the shipped pricing table; unknown prefixes return
    ``None`` and the caller records 0 cost rather than misattributing.
    A follow-up can replace this with an explicit ``X-Conduct-Attempt-Cost-Usd``
    header from the gateway if a future model prefix escapes the map.
    """
    m = (model or "").lower().strip()
    if not m:
        return None
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith(("gpt", "chatgpt", "o1", "o3", "o4", "text-embedding", "text-davinci")):
        return "openai"
    if m.startswith("sonar") or m.startswith("perplexity"):
        return "perplexity"
    if m.startswith(("meta-llama", "mistral", "mixtral", "together")):
        return "together"
    return None


class GatewayProfileClient:
    """LLMClient that dispatches to ``POST /gateway/v1/completions``.

    Mirrors OpenAIClient's public API (``create`` / ``make_assistant_turn`` /
    ``make_tool_results_turn``) so brain_block never branches on transport.
    The only per-call divergence is the wire body: ``profile`` replaces
    ``model`` and the URL path is ``/completions`` instead of
    ``/{provider}/v1/chat/completions``.

    Cost is computed client-side from the response's ``model`` + ``usage``
    so brain_block's per-block ``max_cost_usd`` cap keeps stopping the loop.
    The Gateway audit row also carries an authoritative settled cost per
    attempt; the two are reconciled at ledger time. When the model prefix
    isn't in ``_infer_provider_from_model``'s map the client records 0
    (safer than misattributing) and the cap effectively falls back to
    turn/token caps until the map or a gateway-side header covers the new
    prefix.
    """

    def __init__(
        self,
        *,
        profile_cond_code: str,
        base_url: str,
        default_headers: dict | None = None,
        api_key: str | None = None,
        pricing_snapshot: dict[str, Any] | None = None,
        stream_enabled: bool = False,
    ) -> None:
        # ``api_key`` accepted for interface parity with the sibling adapters
        # (brain_block builds a single kwargs dict). The gateway itself is
        # authenticated via ``default_headers`` (x-conductai-internal token
        # or Authorization: Bearer <run/agent token>), not via api_key.
        _ = api_key
        self._profile = profile_cond_code
        self._base_url = base_url.rstrip("/")
        self._default_headers = default_headers or {}
        self._pricing_snapshot = pricing_snapshot
        # #2170 PR 3 — when True, ``create()`` sends ``stream: true`` +
        # ``stream_options.include_usage: true`` and reassembles the SSE
        # stream into an LLMResponse. Gated by ops per rollout because
        # the canonical shim rejects stream+tools unless
        # ``GUARD_GATEWAY_TOOLS_STREAM_ENABLED`` is set on the gateway
        # (see #2155 buffered-delta validation).
        self._stream_enabled = stream_enabled
        # Sub-identifier used in retry/upstream events so operators can
        # distinguish Gateway-profile failures from direct-provider ones.
        self._provider = "gateway_profile"

    def create(
        self,
        *,
        model: str,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
        max_tokens: int = 4096,
        cache_system: bool = True,
        cache_tools: bool = True,
        idempotency_key: str | None = None,
        on_retry: Callable[[dict[str, Any]], None] | None = None,
        outer_attempt: int = 1,
    ) -> LLMResponse:
        # ``model`` is ignored — the profile picks the model at the gateway.
        # Passed for interface parity so brain_block can build one kwargs
        # dict across all adapters. Cache flags are Anthropic-only concepts;
        # OpenAI's cache is prefix-automatic and the canonical envelope
        # doesn't accept cache_control markers.
        _ = model, cache_system, cache_tools

        # System prompt becomes a system message (canonical is OpenAI-shape).
        oai_messages = [{"role": "system", "content": system}, *messages]

        payload: dict[str, Any] = {
            "profile": self._profile,
            "messages": oai_messages,
            "max_tokens": max_tokens,
            "stream": bool(self._stream_enabled),
        }
        if self._stream_enabled:
            # Without include_usage=true the OpenAI SSE contract omits the
            # usage block entirely on stream responses. brain_block's
            # cost cap needs it; the gateway audit row also relies on
            # it for cost settlement. See canonical shim's identical
            # server-side injection for non-tool /completions calls.
            payload["stream_options"] = {"include_usage": True}
        if tools:
            # Same BRAIN_TOOLS → OpenAI ``functions`` shape OpenAIClient uses.
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                    },
                }
                for t in tools
            ]
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        headers = {
            "Content-Type": "application/json",
            **self._default_headers,
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        # Reviewer P1 (#2182): a canonical response is always an already-paid
        # attempt on the gateway. Its own retry policy (max_attempts on the
        # profile) governs upstream retries. Stacking adapter-level retries
        # on top means a terminal ``conduct_gateway_tool_arguments_validation_failed``
        # 502 (post-inference tool-args refusal) reads as three transient
        # 5xxs and triples the paid inference cost. Force single-shot here.
        _outer_attempt_hint = outer_attempt  # kept for interface parity
        _ = _outer_attempt_hint

        if self._stream_enabled:
            # PR 3 — consume SSE, reassemble text + tool_call deltas into
            # the same OpenAI chat-shape message the non-streaming branch
            # would have received. Correlation header comes off the
            # response before body consumption.
            reassembled, resp_headers = _stream_and_reassemble(
                url=f"{self._base_url}/completions",
                headers={**headers, "Accept": "text/event-stream"},
                payload=payload,
                provider=self._provider,
            )
            raw = reassembled
            _resp_headers = resp_headers
        else:
            r = post_with_retry(
                url=f"{self._base_url}/completions",
                headers=headers,
                json_body=payload,
                provider=self._provider,
                max_attempts=1,
                on_retry=on_retry,
            )
            raise_if_guard_proxy_blocked(provider=self._provider, response=r)
            if r.status_code >= 400:
                raise Exception(f"gateway_profile {r.status_code}: {r.text[:500]}")
            raw = r.json()
            _resp_headers = dict(r.headers) if hasattr(r, "headers") else {}
        choice = ((raw.get("choices") or [{}])[0])
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason") or "stop"

        content: list[LLMTextBlock | LLMToolUseBlock] = []
        text = message.get("content") or ""
        if isinstance(text, str) and text.strip():
            content.append(LLMTextBlock(text=text))

        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments") or "{}"
            try:
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except Exception:
                parsed_args = {}
            content.append(LLMToolUseBlock(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                input=parsed_args if isinstance(parsed_args, dict) else {},
            ))

        u = raw.get("usage") or {}
        usage = LLMUsage(
            input_tokens=int(u.get("prompt_tokens", 0) or 0),
            output_tokens=int(u.get("completion_tokens", 0) or 0),
            cache_read_tokens=0,
            cache_write_tokens=0,
        )

        stop_reason_map = {
            "tool_calls": "tool_use",
            "length": "max_tokens",
            "stop": "end_turn",
        }
        stop_reason = stop_reason_map.get(finish_reason, "end_turn")

        # #2158 — per-tool_call correlation ids ride back on the response
        # header. Parse into {call_id: correlation_id} so brain_block can
        # emit them alongside each tool execution's run_events entry.
        correlation_ids: dict[str, str] = {}
        corr_header = _resp_headers.get("X-Conduct-Tool-Correlation-Ids") or _resp_headers.get("x-conduct-tool-correlation-ids")
        if corr_header:
            try:
                from app.modules.guard.tools_validator import (
                    parse_correlation_header as _parse_corr,
                )
                correlation_ids = _parse_corr(corr_header) or {}
            except Exception:
                # Header shape drift shouldn't fail the whole turn — audit is
                # still complete on the gateway side; the runtime just loses
                # the join key for this call.
                correlation_ids = {}

        # Reviewer P1 (#2182): compute cost client-side from response
        # ``model`` + ``usage`` so brain_block's per-block ``max_cost_usd``
        # cap keeps stopping the loop. Zero here would silently disable
        # the cap for profile-routed workflows.
        upstream_model = raw.get("model") or ""
        provider_hint = _infer_provider_from_model(upstream_model)
        cost_usd = 0.0
        if provider_hint and self._pricing_snapshot is not None:
            rates, _ = get_model_rates(provider_hint, upstream_model, self._pricing_snapshot)
            cost_usd = round((
                usage.input_tokens * float(rates.get("input", 0) or 0)
                + usage.output_tokens * float(rates.get("output", 0) or 0)
            ) / 1_000_000, 6)

        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            usage=usage,
            cost_usd=cost_usd,
            _raw_content=message,
            correlation_ids=correlation_ids,
        )

    def stream(
        self,
        *,
        model: str,
        messages: list[dict],
        system: str,
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        # brain_block's agentic loop only uses create(); this method is
        # here for LLMClient Protocol compliance. If a future caller
        # wants raw text-delta streaming (e.g. a chat surface), set
        # ``stream_enabled=True`` on the client and use create() — it
        # reassembles internally. A yielding stream() adds a second
        # code path with no current consumer.
        raise NotImplementedError(
            "GatewayProfileClient.stream (yield-per-delta) is not wired. "
            "Use create() with stream_enabled=True for reassembled streaming."
        )

    def make_assistant_turn(self, response: LLMResponse) -> list[dict]:
        """Same shape as OpenAIClient — canonical returns OpenAI chat msg."""
        msg = response._raw_content or {}
        out: dict[str, Any] = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            out["tool_calls"] = msg["tool_calls"]
        return [out]

    def make_tool_results_turn(self, results: list[tuple[str, str]]) -> list[dict]:
        """Same shape as OpenAIClient — one role=tool message per result."""
        return [
            {"role": "tool", "tool_call_id": tid, "content": content}
            for tid, content in results
        ]


# ─── SSE reassembly (PR 3) ─────────────────────────────────────────────


def _stream_and_reassemble(
    *,
    url: str,
    headers: dict,
    payload: dict,
    provider: str,
) -> tuple[dict, dict]:
    """POST with stream=true, walk the SSE frames, reassemble to a
    non-streaming OpenAI chat-completion shape. Returns ``(reassembled_json,
    response_headers_dict)``.

    The output shape matches what the non-streaming branch consumes so the
    downstream mapping (tool_use blocks, cost, correlation) doesn't
    branch on transport:

        {
          "id": "...",
          "model": "<upstream-model>",
          "choices": [{
            "message": {"content": "...", "tool_calls": [...]},
            "finish_reason": "stop" | "tool_calls" | "length"
          }],
          "usage": {"prompt_tokens": N, "completion_tokens": M}
        }

    Tool-call reassembly: OpenAI's streaming contract sends the
    ``id``/``name``/``type`` once on the first delta for a given index
    and then fragments ``function.arguments`` across many deltas.
    We accumulate by ``index`` and only emit each call once at the end.
    ``usage`` arrives in the final data chunk when ``stream_options.
    include_usage: true`` was set on the request; without it, cost stays
    at 0 and brain_block's cost cap loses that turn.

    Errors: an early non-2xx returns the body verbatim (no retry — the
    non-streaming branch owns that policy, and streaming inference is
    already partly paid). Any exception aborts the stream.
    """
    import httpx as _httpx

    _text_parts: list[str] = []
    _tool_calls_by_index: dict[int, dict[str, Any]] = {}
    _finish_reason: str | None = None
    _usage: dict[str, Any] = {}
    _model: str = ""
    _id: str = ""
    _resp_headers: dict[str, str] = {}

    with _httpx.stream(
        "POST", url, headers=headers, json=payload,
        timeout=_httpx.Timeout(600.0),
    ) as resp:
        _resp_headers = {k: v for k, v in resp.headers.items()}
        if resp.status_code >= 400:
            body = b""
            for _chunk in resp.iter_bytes():
                body += _chunk
            raise Exception(
                f"{provider} {resp.status_code}: "
                f"{body[:500].decode(errors='replace')}"
            )

        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue

            # Top-level id/model are echoed on every chunk; last one wins
            # (they're the same in practice, but be robust).
            if isinstance(obj.get("id"), str):
                _id = obj["id"]
            if isinstance(obj.get("model"), str):
                _model = obj["model"]

            # Final usage chunk (stream_options.include_usage=true).
            if isinstance(obj.get("usage"), dict):
                _usage = obj["usage"]

            for choice in obj.get("choices") or []:
                if choice.get("finish_reason"):
                    _finish_reason = choice["finish_reason"]
                delta = choice.get("delta") or {}
                # Text content — plain accumulation.
                if isinstance(delta.get("content"), str):
                    _text_parts.append(delta["content"])
                # Tool call fragments — merge by index.
                for tc in delta.get("tool_calls") or []:
                    if not isinstance(tc, dict):
                        continue
                    idx = tc.get("index")
                    if not isinstance(idx, int):
                        continue
                    slot = _tool_calls_by_index.setdefault(idx, {
                        "id": "", "type": "function",
                        "function": {"name": "", "arguments": ""},
                    })
                    if isinstance(tc.get("id"), str) and tc["id"]:
                        slot["id"] = tc["id"]
                    if isinstance(tc.get("type"), str) and tc["type"]:
                        slot["type"] = tc["type"]
                    fn_frag = tc.get("function") or {}
                    if isinstance(fn_frag, dict):
                        if isinstance(fn_frag.get("name"), str) and fn_frag["name"]:
                            slot["function"]["name"] = fn_frag["name"]
                        if isinstance(fn_frag.get("arguments"), str):
                            # Accumulate — arguments arrive as JSON string
                            # deltas that concatenate into a valid object.
                            slot["function"]["arguments"] += fn_frag["arguments"]

    message: dict[str, Any] = {"content": "".join(_text_parts) or None}
    if _tool_calls_by_index:
        # Emit in index order so the downstream normaliser sees a stable
        # sequence matching the upstream contract.
        message["tool_calls"] = [
            _tool_calls_by_index[k] for k in sorted(_tool_calls_by_index.keys())
        ]

    return (
        {
            "id": _id,
            "model": _model,
            "choices": [{
                "message": message,
                "finish_reason": _finish_reason or "stop",
            }],
            "usage": _usage,
        },
        _resp_headers,
    )
