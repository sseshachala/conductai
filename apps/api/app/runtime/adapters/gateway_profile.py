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
            "stream": False,
        }
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
        corr_header = r.headers.get("X-Conduct-Tool-Correlation-Ids") if hasattr(r, "headers") else None
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
        # ponytail: streaming lands in the follow-up PR. brain_block's
        # agentic loop doesn't call stream() today, so this is a "raise
        # if you get here" surface, not a hot path.
        raise NotImplementedError(
            "GatewayProfileClient.stream is not implemented — streaming through "
            "the canonical /completions shim needs SSE reassembly of "
            "delta.tool_calls[].function.arguments (see follow-up to #2170)."
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
