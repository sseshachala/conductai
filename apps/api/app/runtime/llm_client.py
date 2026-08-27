"""
LLM client abstraction — provider-agnostic interface for Brain block LLM calls.

Each adapter implements three methods:
  create()                — issue one call, return normalized LLMResponse (with cost_usd)
  make_assistant_turn()   — format the assistant's response for conversation history
  make_tool_results_turn()— format tool results for conversation history

Message format differs by provider:
  Anthropic: tool results -> single {"role": "user", "content": [tool_result, ...]}
  OpenAI:    tool results -> one {"role": "tool", ...} message per result

Both make_* methods return list[dict] so the executor always does messages.extend(...).

Adding a new provider: implement LLMClient, add to adapters/, register in client_for().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Protocol, runtime_checkable


# ── Normalized response types ─────────────────────────────────────────────────

@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0    # prompt-cache read hits (Anthropic only; 0 for others)
    cache_write_tokens: int = 0   # prompt-cache write cost (Anthropic only; 0 for others)


@dataclass
class LLMTextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class LLMToolUseBlock:
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: list[LLMTextBlock | LLMToolUseBlock]
    stop_reason: str        # normalized: "end_turn" | "tool_use" | "max_tokens"
    usage: LLMUsage
    cost_usd: float = 0.0  # computed by adapter from usage + model pricing; executor sums across turns
    _raw_content: Any = field(default=None, repr=False)  # provider-native content; used by make_assistant_turn

    def to_cache_dict(self) -> dict:
        def _block_to_dict(b: Any) -> dict:
            if hasattr(b, "model_dump"):
                return b.model_dump()
            if isinstance(b, (LLMTextBlock, LLMToolUseBlock)):
                return b.__dict__
            return b if isinstance(b, dict) else {}

        raw = [_block_to_dict(b) for b in self._raw_content] if self._raw_content else None
        return {
            "content": [c.__dict__ for c in self.content],
            "stop_reason": self.stop_reason,
            "usage": self.usage.__dict__,
            "cost_usd": self.cost_usd,
            "_raw_content": raw,
        }

    @classmethod
    def from_cache_dict(cls, d: dict) -> "LLMResponse":
        usage = LLMUsage(**d["usage"])
        content = [
            LLMToolUseBlock(**b) if b.get("type") == "tool_use" else LLMTextBlock(**b)
            for b in d["content"]
        ]
        return cls(
            content=content,
            stop_reason=d["stop_reason"],
            usage=usage,
            cost_usd=d.get("cost_usd", 0.0),
            _raw_content=d.get("_raw_content"),  # plain dicts — accepted by Anthropic/OpenAI APIs
        )


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class LLMClient(Protocol):
    def create(
        self,
        *,
        model: str,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
        max_tokens: int = 4096,
        cache_system: bool = False,
        idempotency_key: str | None = None,
        on_retry: Callable[[dict[str, Any]], None] | None = None,
    ) -> LLMResponse:
        """
        Issue one LLM call and return a normalized LLMResponse.

        Args:
            model:        Model ID string (as returned by model_router.resolve)
            messages:     Conversation history — [{"role": "user"|"assistant", "content": ...}]
            system:       System prompt as a plain string; adapter handles caching internally
            tools:        Tool definitions in BRAIN_TOOLS format (name/description/input_schema).
                          None for single-shot (non-agentic) calls.
            tool_choice:  Force a specific tool (e.g. {"type": "tool", "name": "foo"}) or
                          {"type": "any"} to force any tool. None = let model decide.
            max_tokens:   Max tokens for this response
            cache_system: When True, adapter wraps system prompt with cache_control so
                          turns 2-N in an agentic loop read from cache (~10% cost)
        """
        ...

    def stream(
        self,
        *,
        model: str,
        messages: list[dict],
        system: str,
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        """
        Streaming variant of create(). Yields text deltas as they arrive.

        No tools, no tool_choice — streaming is text-only. If you need
        structured/tool output, use create() (non-streaming).

        Implemented by AnthropicClient (native SDK) and OpenAIClient (raw
        SSE via httpx — covers openai, perplexity, together, and any other
        OpenAI-compatible /v1/chat/completions endpoint).
        """
        ...

    def make_assistant_turn(self, response: LLMResponse) -> list[dict]:
        """
        Return the message(s) representing the assistant's turn, ready to extend messages[].

        Anthropic: [{"role": "assistant", "content": <raw content blocks>}]
        OpenAI:    [{"role": "assistant", "content": text, "tool_calls": [...]}]
        """
        ...

    def make_tool_results_turn(self, results: list[tuple[str, str]]) -> list[dict]:
        """
        Return the message(s) that deliver tool results back to the model.

        Args:
            results: list of (tool_use_id, result_content_str)

        Anthropic: [{"role": "user", "content": [{"type": "tool_result", ...}, ...]}]  — one batched message
        OpenAI:    [{"role": "tool", "tool_call_id": id, "content": result}, ...]      — one message per result
        """
        ...


# ── Upstream failure handling ─────────────────────────────────────────────────
# When an LLM proxy request is intercepted by CF/Render infrastructure (WAF,
# deploy transition, edge outage) we receive HTML instead of a JSON error. The
# raw HTML must not leak into customer-visible run events. LLMUpstreamError
# gives us a bounded, structured failure that stringifies cleanly.

class GuardProxyBlocked(Exception):
    """Conduct proxy issued a structured policy/config block (not transport failure).

    Distinct from LLMUpstreamError (infra hiccup) — this is a deliberate
    decision by the proxy: Guard policy fired, or a proxy configuration
    error prevents the request. The str(exc) is shaped to match the
    "[ConductGuard] Blocked by policy" pattern that dag_runner._classify_failure
    already recognises, so these surface with the Guard UX path automatically.
    """

    def __init__(self, *, provider: str, status: int, error_type: str,
                 message: str, rule_id: str | None = None) -> None:
        self.provider = provider
        self.status = status
        self.error_type = error_type
        self.rule_id = rule_id
        self.message = message
        # Shape the string so _classify_failure's existing Guard branch matches
        # when error_type is guard_block. For conduct_guard_proxy (config error),
        # emit a distinguishable message.
        if error_type == "guard_block":
            rule_part = f" policy '{rule_id}'" if rule_id else ""
            super().__init__(f"[ConductGuard] Blocked by{rule_part}: {message}")
        else:
            super().__init__(f"[ConductProxy] {error_type}: {message}")


class LLMUpstreamError(Exception):
    """LLM proxy returned an intercepted/upstream failure (not a real provider error).

    Distinguished from real provider errors (auth, invalid request, model errors)
    which stay as their normal exception types. This one signals an infra issue:
    CF WAF, Render edge, transient 5xx from something between us and the provider.
    """

    def __init__(self, *, provider: str, status: int, content_type: str,
                 body_snippet: str,
                 cf_ray: str | None, request_id: str | None,
                 attempts: int) -> None:
        self.provider = provider
        self.status = status
        self.content_type = content_type
        self.body_snippet = _sanitize_body_snippet(body_snippet)
        self.cf_ray = cf_ray
        self.request_id = request_id
        self.attempts = attempts
        super().__init__(
            f"{provider} upstream blocked: HTTP {status} after {attempts} attempts "
            f"(cf_ray={cf_ray or 'none'}, render_req={request_id or 'none'})"
        )


_RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504, 529}


def _sanitize_body_snippet(body: str, limit: int = 2000) -> str:
    """Return bounded plain text suitable for logs and customer-visible events.

    Order matters: fully decode HTML entities BEFORE stripping tags so
    entity-encoded payloads (`&lt;script&gt;`, `&amp;lt;script&amp;gt;`)
    can't smuggle real tags past the stripper into an event body that a
    dashboard might render live.

    Loops the decode step until stable (with a small ceiling) to handle
    multi-encoded payloads without runaway.
    """
    import html as _html
    import re as _re

    text = body or ""
    # 1. Decode entities repeatedly until stable, capped at 5 rounds so a
    #    pathological input cannot spin.
    for _ in range(5):
        decoded = _html.unescape(text)
        if decoded == text:
            break
        text = decoded
    # 2. Strip script/style bodies (may contain executable content).
    text = _re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", text)
    # 3. Strip remaining tags.
    text = _re.sub(r"(?s)<[^>]+>", " ", text)
    # 4. Drop non-printable characters, collapse whitespace, bound length.
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    return _re.sub(r"\s+", " ", text).strip()[:limit]


def make_retry_info(
    *,
    provider: str,
    status: int,
    content_type: str,
    attempt: int,
    max_attempts: int,
    cf_ray: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """One-stop constructor for the retry-info dict passed to on_retry callbacks.

    Adapters and post_with_retry call this so the payload shape stays identical
    across sites. Brain block's llm_upstream_retry event and any downstream
    dashboards can rely on a stable schema.
    """
    return {
        "provider": provider,
        "status": status,
        "content_type": content_type,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "cf_ray": cf_ray,
        "request_id": request_id,
    }


def _is_html_response(status: int, content_type: str) -> bool:
    """HTML on a 4xx/5xx = something upstream (CF, Render, WAF) intercepted us.

    Real provider errors are JSON. HTML at these status codes means the request
    never reached (or the response never returned from) our FastAPI app.
    """
    return status >= 400 and "text/html" in (content_type or "").lower()


def _is_permanent_proxy_error(content_type: str, body: str) -> bool:
    """Conduct proxy configuration/policy errors are structured and non-transient."""
    if "json" not in (content_type or "").lower() or not body:
        return False
    import json as _json
    try:
        payload = _json.loads(body)
    except (TypeError, ValueError):
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    error_type = error.get("type") if isinstance(error, dict) else None
    return error_type in {"conduct_guard_proxy", "guard_block"}


def raise_if_guard_proxy_blocked(*, provider: str, response: "Any") -> None:
    """Inspect a response for a Conduct proxy structured block and raise
    GuardProxyBlocked if matched. Otherwise return (caller handles response).

    Called by every adapter after post_with_retry returns — turns the JSON
    error body into a typed exception dag_runner._classify_failure can route
    through the existing Guard UX path.
    """
    try:
        content_type = response.headers.get("content-type", "")
        body = response.text
    except Exception:
        return
    if not _is_permanent_proxy_error(content_type, body):
        return
    import json as _json
    try:
        payload = _json.loads(body)
    except (TypeError, ValueError):
        return
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return
    error_type = error.get("type") or ""
    message = error.get("message") or error.get("detail") or "Blocked by Conduct proxy"
    rule_id = error.get("rule_id") or error.get("policy_id")
    status = getattr(response, "status_code", 0) or 0
    raise GuardProxyBlocked(
        provider=provider, status=status, error_type=error_type,
        message=message, rule_id=rule_id,
    )


def _should_retry(status: int, content_type: str, body: str = "") -> bool:
    """Retry only on transient/infra failures, never on real client errors.

    Retry: 408, 429, 5xx, or HTML 403 (WAF-shaped)
    NEVER retry: JSON 4xx (auth, bad request, quota) — retries would DoS the
    provider or spin on a revoked key.
    """
    if _is_permanent_proxy_error(content_type, body):
        return False
    if status in _RETRYABLE_STATUSES:
        return True
    if status == 403 and _is_html_response(status, content_type):
        return True
    return False


def _extract_upstream_ids(headers: dict, body: str) -> tuple[str | None, str | None]:
    """Pull cf-ray from headers (authoritative) and Render request ID from HTML body.

    Header-first is safer: headers are set by the CF/Render infra we're
    diagnosing, HTML format can change. Body regex is fallback.
    """
    import re as _re
    cf_ray = None
    # httpx headers are case-insensitive dict-like; str() on the dict may
    # lose that, so try common cases.
    for key in ("cf-ray", "CF-Ray", "Cf-Ray"):
        if isinstance(headers, dict):
            v = headers.get(key)
            if v:
                cf_ray = v
                break
        else:
            # httpx.Headers — case-insensitive access
            v = headers.get(key)  # type: ignore[union-attr]
            if v:
                cf_ray = v
                break

    request_id = None
    for key in ("x-request-id", "request-id", "rndr-id", "x-render-request-id"):
        value = headers.get(key)
        if value:
            request_id = value
            break
    if body:
        m = _re.search(r"Request ID:\s*<code[^>]*>([a-z0-9-]+)</code>", body, _re.IGNORECASE)
        if m:
            request_id = request_id or m.group(1)
        elif request_id is None:
            # Also try Render's rndr-id header style embedded in body
            m2 = _re.search(r"rndr-id[:\s]+([a-f0-9\-]+)", body, _re.IGNORECASE)
            if m2:
                request_id = m2.group(1)
    return cf_ray, request_id


def post_with_retry(
    *,
    url: str,
    headers: dict,
    json_body: dict,
    provider: str,
    timeout: float = 60.0,
    max_attempts: int = 3,
    on_retry: Callable[[dict[str, Any]], None] | None = None,
) -> "Any":
    """POST with retry on transient upstream failures. Returns httpx.Response.

    Raises LLMUpstreamError if all attempts return retryable failures.
    Non-retryable errors (JSON 4xx, network errors after final attempt) are
    returned as-is or raised by httpx.

    Retry schedule: honors Retry-After header when present, else exponential
    backoff (250ms, 1s, 4s) with jitter. Capped at 10s per wait.
    """
    import httpx as _httpx
    import random as _random
    import time as _time

    last_resp = None
    for attempt in range(max_attempts):
        try:
            resp = _httpx.post(url, headers=headers, json=json_body, timeout=timeout)
        except (_httpx.ConnectError, _httpx.ReadTimeout, _httpx.RemoteProtocolError) as exc:
            # Network-level transient failure — retry unless last attempt
            if attempt == max_attempts - 1:
                raise LLMUpstreamError(
                    provider=provider,
                    status=0,
                    content_type="",
                    body_snippet=f"network error: {exc!s:.200}",
                    cf_ray=None,
                    request_id=None,
                    attempts=attempt + 1,
                )
            if on_retry:
                on_retry(make_retry_info(
                    provider=provider, status=0, content_type="",
                    attempt=attempt + 1, max_attempts=max_attempts,
                ))
            _time.sleep(min(0.25 * (4 ** attempt) + _random.random() * 0.2, 10))
            continue

        content_type = resp.headers.get("content-type", "")
        if not _should_retry(resp.status_code, content_type, resp.text):
            return resp  # success OR real error — caller decides

        last_resp = resp
        if attempt == max_attempts - 1:
            cf_ray, request_id = _extract_upstream_ids(dict(resp.headers), resp.text)
            raise LLMUpstreamError(
                provider=provider,
                status=resp.status_code,
                content_type=content_type,
                body_snippet=resp.text,
                cf_ray=cf_ray,
                request_id=request_id,
                attempts=attempt + 1,
            )

        cf_ray, request_id = _extract_upstream_ids(resp.headers, resp.text)
        if on_retry:
            on_retry(make_retry_info(
                provider=provider, status=resp.status_code,
                content_type=content_type, attempt=attempt + 1,
                max_attempts=max_attempts, cf_ray=cf_ray, request_id=request_id,
            ))

        # Honor Retry-After if present, else exponential backoff with jitter
        retry_after = resp.headers.get("retry-after")
        try:
            sleep_sec = float(retry_after) if retry_after else (0.25 * (4 ** attempt))
        except ValueError:
            sleep_sec = 0.25 * (4 ** attempt)
        sleep_sec += _random.random() * 0.2  # jitter
        _time.sleep(min(sleep_sec, 10))

    # Shouldn't reach here — either returned or raised. But be safe.
    if last_resp is not None:
        cf_ray, request_id = _extract_upstream_ids(dict(last_resp.headers), last_resp.text)
        raise LLMUpstreamError(
            provider=provider,
            status=last_resp.status_code,
            content_type=last_resp.headers.get("content-type", ""),
            body_snippet=last_resp.text,
            cf_ray=cf_ray,
            request_id=request_id,
            attempts=max_attempts,
        )
    raise RuntimeError(f"post_with_retry: exhausted without response, provider={provider}")


# ── Factory ───────────────────────────────────────────────────────────────────

def client_for(provider: str, api_key: str, pricing_snapshot: dict[str, Any] | None = None, base_url: str | None = None) -> LLMClient:
    """
    Return the correct adapter instance for the given provider slug.

    Args:
        provider:          One of "anthropic", "openai", "perplexity"
        api_key:           Provider API key (decrypted at point of use — never stored)
        pricing_snapshot:  Optional frozen pricing dict from freeze_pricing_snapshot()
        base_url:          Optional override (e.g. Guard proxy URL)

    Raises:
        ValueError: if provider is unrecognised
    """
    if provider == "anthropic":
        from app.runtime.adapters.anthropic import AnthropicClient
        return AnthropicClient(api_key=api_key, pricing_snapshot=pricing_snapshot, base_url=base_url)
    if provider == "openai":
        from app.runtime.adapters.openai import OpenAIClient
        return OpenAIClient(api_key=api_key, pricing_snapshot=pricing_snapshot, base_url=base_url)
    if provider == "perplexity":
        from app.runtime.adapters.perplexity import PerplexityClient
        return PerplexityClient(api_key=api_key, pricing_snapshot=pricing_snapshot, base_url=base_url)
    if provider == "together":
        from app.runtime.adapters.together import TogetherClient
        return TogetherClient(api_key=api_key, pricing_snapshot=pricing_snapshot, base_url=base_url)
    raise ValueError(f"Unknown LLM provider: {provider!r}. Expected one of: anthropic, openai, perplexity, together")


# ── Re-exports for backward compatibility ─────────────────────────────────────
# Existing imports like `from app.runtime.llm_client import AnthropicClient` continue to work.

from app.runtime.adapters.anthropic import AnthropicClient as AnthropicClient    # noqa: E402, F401
from app.runtime.adapters.openai import OpenAIClient as OpenAIClient              # noqa: E402, F401
from app.runtime.adapters.perplexity import PerplexityClient as PerplexityClient  # noqa: E402, F401
from app.runtime.adapters.together import TogetherClient as TogetherClient        # noqa: E402, F401
