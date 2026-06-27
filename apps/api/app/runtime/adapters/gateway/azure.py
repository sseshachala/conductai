"""Azure OpenAI gateway adapter.

Azure requires the key in `api-key`, not `Authorization: Bearer`.
The `provider` argument is ignored — Azure is always OpenAI-compatible.
The model argument is the deployment name, configured in the brain block.
"""

from __future__ import annotations

from app.runtime.adapters.gateway._types import GatewayConfig


def adapt(api_key: str, provider: str, model: str) -> GatewayConfig:
    # Azure model = deployment name; user is expected to set model = deployment name in brain block
    return GatewayConfig(
        headers={"api-key": api_key},
        model=model,
    )
