"""Qwen3 inference client for GLens."""
import time
import uuid

import structlog
from openai import OpenAI

from app.core.config import settings

log = structlog.get_logger(__name__)

_DECISION_NORMALIZE = {"block": "blocked", "warn": "warned", "audit": "audited", "allow": "allowed"}


def get_client() -> OpenAI:
    """Create a fresh OpenAI client each call — cheap, avoids stale credentials on rotation."""
    if not settings.conduct_inference_endpoint_url:
        raise RuntimeError("CONDUCT_INFERENCE_ENDPOINT_URL not configured")
    base_url = settings.conduct_inference_endpoint_url
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    api_key = settings.conduct_inference_token_id or "unused"
    extra: dict = {}
    if settings.conduct_inference_token_secret:
        extra["default_headers"] = {
            "Modal-Key": settings.conduct_inference_token_id,
            "Modal-Secret": settings.conduct_inference_token_secret,
        }
    return OpenAI(base_url=base_url, api_key=api_key, **extra)


def chat_with_tools(messages: list[dict], tools: list[dict], session_id: str | None = None):
    """Returns the raw message object (.content and .tool_calls)."""
    sid = session_id or str(uuid.uuid4())
    log.debug("glens.inference.tool_request", session_id=sid, turns=len(messages))
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            response = get_client().chat.completions.create(
                model=settings.conduct_inference_model_name,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
                max_tokens=2048,
                timeout=120,
                extra_body={"thinking": {"type": "disabled"}},
            )
            msg = response.choices[0].message
            log.debug("glens.inference.tool_response", session_id=sid, finish_reason=response.choices[0].finish_reason)
            return msg
        except Exception as e:
            last_exc = e
            if attempt == 0:
                log.warning("glens.inference.tool_error_retry", session_id=sid, attempt=attempt, error=str(e))
                time.sleep(2)
    log.warning("glens.inference.tool_error", session_id=sid, error=str(last_exc))
    raise last_exc


def chat(messages: list[dict], session_id: str | None = None) -> str:
    sid = session_id or str(uuid.uuid4())
    log.debug("glens.inference.request", session_id=sid, turns=len(messages))
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            response = get_client().chat.completions.create(
                model=settings.conduct_inference_model_name,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=1024,
                timeout=90,
                extra_body={"thinking": {"type": "disabled"}},
            )
            content = response.choices[0].message.content.strip()
            log.debug("glens.inference.response", session_id=sid, length=len(content))
            return content
        except Exception as e:
            last_exc = e
            if attempt == 0:
                log.warning("glens.inference.error_retry", session_id=sid, attempt=attempt, error=str(e))
                time.sleep(2)
    log.warning("glens.inference.error", session_id=sid, error=str(last_exc))
    raise last_exc
