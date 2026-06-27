"""Azure OpenAI gateway adapter.

Azure requires the key in `api-key`, not `Authorization: Bearer`.
The `provider` argument is ignored — Azure is always OpenAI-compatible.
"""


def headers(api_key: str, provider: str) -> dict:
    return {"api-key": api_key}
