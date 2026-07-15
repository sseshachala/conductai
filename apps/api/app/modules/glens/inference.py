"""
Qwen3 inference client for GLens.
All calls route through Modal endpoint — data never sent to model.
"""
import uuid
from openai import OpenAI
from app.core.config import settings

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.conduct_inference_endpoint_url:
            raise RuntimeError("CONDUCT_INFERENCE_ENDPOINT_URL not configured")
        base_url = settings.conduct_inference_endpoint_url
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        _client = OpenAI(
            base_url=base_url,
            api_key="unused",
            default_headers={
                "Modal-Key": settings.conduct_inference_token_id,
                "Modal-Secret": settings.conduct_inference_token_secret,
            },
        )
    return _client


def chat(messages: list[dict], session_id: str | None = None) -> str:
    client = get_client()
    response = client.chat.completions.create(
        model=settings.conduct_inference_model_name,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=1024,
        extra_headers={"Modal-Session-ID": session_id or str(uuid.uuid4())},
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        timeout=90,
    )
    return response.choices[0].message.content.strip()
