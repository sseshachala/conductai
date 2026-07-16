"""Qwen3 inference client for GLens."""
import uuid
from functools import lru_cache

import structlog
from openai import OpenAI

from app.core.config import settings

log = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    if not settings.conduct_inference_endpoint_url:
        raise RuntimeError("CONDUCT_INFERENCE_ENDPOINT_URL not configured")
    base_url = settings.conduct_inference_endpoint_url
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return OpenAI(
        base_url=base_url,
        api_key="unused",
        default_headers={
            "Modal-Key": settings.conduct_inference_token_id,
            "Modal-Secret": settings.conduct_inference_token_secret,
        },
    )


def chat(messages: list[dict], session_id: str | None = None) -> str:
    sid = session_id or str(uuid.uuid4())
    log.debug("glens.inference.request", session_id=sid, turns=len(messages))
    try:
        response = get_client().chat.completions.create(
            model=settings.conduct_inference_model_name,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1024,
            extra_headers={"Modal-Session-ID": sid},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            timeout=90,
        )
        content = response.choices[0].message.content.strip()
        log.debug("glens.inference.response", session_id=sid, length=len(content))
        return content
    except Exception as e:
        log.warning("glens.inference.error", session_id=sid, error=str(e))
        raise
