"""Minimal v2 request-path wire-in (#2001 review fix, part of commit 5).

The v2 Gateway Profile + attempt coordinator now execute real client
traffic when both of these are true for the incoming request:

    settings.guard_gateway_profile_v2 = True
    body["model"] resolves to a published binding for this
    (workspace, environment)

Otherwise the caller falls through to the legacy v1 path. Nothing about
the flag-off default changes.

Scope of this initial wire:

- Non-streaming inference only. Streaming paths need the
  "no attempt N+1 after first byte" invariant which the current
  `_stream_chunks` implementation owns; wiring it through the
  coordinator is a follow-up.
- ``anthropic_messages``, ``openai_chat_completions``, ``openai_responses``,
  ``anthropic_count_tokens`` — mapped from URL provider + upstream_path.
- LiteLLM SDK transport only. HTTP passthrough targets raise
  ``UnsupportedTransport`` from the coordinator (publish-gate should
  have caught this configuration anyway).

Failure classification:

- Body missing ``model`` field → not our path; return None so the caller
  falls through to v1.
- v2 flag off or resolve_v2 returns None → return None; caller falls
  through.
- Coordinator succeeds → JSONResponse with the LiteLLM response body
  and ``routing_meta.v2 = {revision_id, attempts, winning_target_id}``
  pinned via the caller's audit lifecycle.
- Coordinator fails all attempts → fail-closed 502 with attempt summary
  in the body; audit is written by the caller.
"""
from __future__ import annotations

from typing import Any

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.guard.gateway_config import Operation, parse_credential_ref
from app.modules.guard.gateway_runtime import ResolvedV2, resolve_v2
from app.runtime.attempt_coordinator import (
    AllAttemptsFailed,
    AttemptCoordinator,
    CoordinatorResult,
    UnsupportedTransport,
)
from app.runtime.litellm_transport import CredentialResolver


log = structlog.get_logger(__name__)


# One coordinator per worker — targets stateless dispatch only.
_COORDINATOR = AttemptCoordinator()


def _operation_from(provider: str, upstream_path: str) -> Operation | None:
    """Map (URL provider surface, upstream path) → v2 operation enum.

    Returns None for operations we haven't wired yet — the caller falls
    through to v1 so behavior is unchanged for those routes.
    """
    if provider == "anthropic":
        if upstream_path == "/v1/messages":
            return "anthropic_messages"
        if upstream_path == "/v1/messages/count_tokens":
            return "anthropic_count_tokens"
    if provider == "openai":
        if upstream_path == "/v1/chat/completions":
            return "openai_chat_completions"
        if upstream_path == "/v1/responses":
            return "openai_responses"
    return None


def _make_credential_resolver(
    db: Session, workspace_id: str,
) -> CredentialResolver:
    """Build a resolver closure. Vault decryption happens only inside
    the closure, and the closure isn't held past the request scope, so
    plaintext credentials don't outlive the attempt."""
    from app.core.credentials import get_vault_credential

    def _resolve(ref: str) -> str:
        env_id, name = parse_credential_ref(ref)
        creds = get_vault_credential(db, workspace_id, str(env_id), name)
        # Vault stores by handle; the common LLM shape is
        # ``{"api_key": "sk-..."}`` but some integrations use ``token``.
        for field in ("api_key", "API_KEY", "token", "TOKEN"):
            value = creds.get(field)
            if value:
                return str(value)
        raise ValueError(
            f"Vault entry {ref!r} has no ``api_key``/``token`` field — "
            f"check the credential in Settings → Vault"
        )
    return _resolve


async def maybe_handle_v2(
    *,
    request: Request,
    db: Session,
    workspace_id: str,
    environment_id: str | None,
    body: dict[str, Any],
    provider: str,
    upstream_path: str,
    routing_meta_sink: dict[str, Any],
) -> JSONResponse | None:
    """Try to serve this request via the v2 path.

    Returns a JSONResponse if v2 handled the request (success or fail-
    closed). Returns None if v2 wasn't applicable — the caller should
    continue with the legacy v1 pipeline unchanged.

    ``routing_meta_sink`` is a caller-supplied dict; on success we
    mutate it to add ``routing_meta_sink["v2"] = {revision_id,
    winning_target_id, attempts: [...]}``. Callers pass this through to
    the durable-audit writer so v2 attribution shows up in Flight
    Recorder.
    """
    # 1. Flag gate. Off = full fall-through, no cost.
    if not settings.guard_gateway_profile_v2:
        return None

    # 2. Environment gate. v2 bindings key on (workspace, env, alias);
    #    a request that didn't pin an env can't resolve.
    if not environment_id:
        return None

    # 3. model_alias comes from the body's model field, per the design.
    #    Unknown/missing → fall through so v1 handles it.
    model_alias = body.get("model")
    if not isinstance(model_alias, str) or not model_alias.strip():
        return None
    model_alias = model_alias.strip()

    # 4. Operation gate. If we haven't wired the operation, don't
    #    intercept — v1 continues to serve it as before.
    operation = _operation_from(provider, upstream_path)
    if operation is None:
        return None

    # 5. Streaming gate. Body's ``stream`` flag = true → v1 for now.
    if body.get("stream"):
        return None

    # 6. Binding lookup. No binding for (workspace, env, alias) → this
    #    is the "unknown model" case a v2-enabled workspace should
    #    surface as 400 rather than falling back to v1 silently.
    resolved: ResolvedV2 | None = resolve_v2(
        db,
        workspace_id=workspace_id,
        environment_id=environment_id,
        model_alias=model_alias,
    )
    if resolved is None:
        # Fail-closed with a specific error naming the alias the client
        # asked for. Falling through to v1 here would defeat the whole
        # point of the flag being on.
        log.info(
            "gateway.v2.no_binding",
            workspace_id=workspace_id,
            environment_id=environment_id,
            model_alias=model_alias,
        )
        return JSONResponse(
            status_code=400,
            content={
                "type": "error",
                "error": {
                    "type": "unknown_model",
                    "message": (
                        f"model {model_alias!r} is not published in "
                        f"this environment. Add a Gateway Profile with "
                        f"``model_alias={model_alias!r}`` and publish it."
                    ),
                },
            },
        )

    # 7. Check the profile advertises this operation.
    if operation not in resolved.profile.accepts:
        return JSONResponse(
            status_code=400,
            content={
                "type": "error",
                "error": {
                    "type": "operation_not_accepted",
                    "message": (
                        f"model {model_alias!r} is published without "
                        f"``{operation}`` in accepts; the client asked for "
                        f"an operation the profile does not serve."
                    ),
                },
            },
        )

    # 8. Execute via the coordinator.
    credential_resolver = _make_credential_resolver(db, workspace_id)
    try:
        result: CoordinatorResult = await _COORDINATOR.execute(
            resolved=resolved,
            operation=operation,
            payload=body,
            credential_resolver=credential_resolver,
            stream=False,
        )
    except UnsupportedTransport as exc:
        log.error(
            "gateway.v2.unsupported_transport",
            workspace_id=workspace_id, model_alias=model_alias,
            err=str(exc),
        )
        return JSONResponse(
            status_code=502,
            content={
                "type": "error",
                "error": {
                    "type": "unsupported_target",
                    "message": str(exc),
                },
            },
        )
    except AllAttemptsFailed as exc:
        # Pin what we can into routing_meta for audit, then fail closed
        # with a summary so operators can grep by target id in logs.
        routing_meta_sink["v2"] = {
            "revision_id": str(resolved.revision_id),
            "winning_target_id": None,
            "attempts": [
                {
                    "target_id": a.target_id,
                    "transport": a.transport,
                    "provider_or_integration": a.provider_or_integration,
                    "succeeded": a.succeeded,
                    "error_class": a.error_class,
                    "error_summary": a.error_summary,
                }
                for a in exc.attempts
            ],
        }
        log.warning(
            "gateway.v2.all_attempts_failed",
            workspace_id=workspace_id, model_alias=model_alias,
            revision_id=str(resolved.revision_id),
        )
        return JSONResponse(
            status_code=502,
            content={
                "type": "error",
                "error": {
                    "type": "upstream_unavailable",
                    "message": str(exc),
                },
            },
        )

    # 9. Success. Pin attribution and return the wire-format body.
    routing_meta_sink["v2"] = {
        "revision_id": str(result.revision_id),
        "winning_target_id": result.winning_target_id,
        "attempts": [
            {
                "target_id": a.target_id,
                "transport": a.transport,
                "provider_or_integration": a.provider_or_integration,
                "succeeded": a.succeeded,
                "error_class": a.error_class,
                "error_summary": a.error_summary,
            }
            for a in result.attempts
        ],
    }

    # LiteLLM returns typed response objects that JSON-serialize fine
    # via Pydantic. Best-effort model_dump when the response supports
    # it; otherwise fall through to a generic dict cast.
    payload = _serialize_response(result.response)
    log.info(
        "gateway.v2.served",
        workspace_id=workspace_id, model_alias=model_alias,
        winning_target=result.winning_target_id,
        attempts=len(result.attempts),
    )
    return JSONResponse(status_code=200, content=payload)


def _serialize_response(obj: Any) -> Any:
    """Coerce a LiteLLM response into a JSON-friendly dict.

    LiteLLM returns Pydantic models for most operations; a few (like
    token counting) return primitives. Cover both without importing
    LiteLLM's specific types here — keeps this module test-friendly
    without a LiteLLM install.
    """
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, (dict, list, str, int, float, bool)) or obj is None:
        return obj
    # Last resort — try dict(obj) and fall back to str()
    try:
        return dict(obj)
    except Exception:  # noqa: BLE001
        return {"result": str(obj)}


__all__ = ["maybe_handle_v2"]
