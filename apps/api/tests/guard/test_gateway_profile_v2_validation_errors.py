"""PR 6 — structured per-target validation errors for Gateway Profile v2.

Locks the response shape the editor UI depends on so it can highlight
the offending target row rather than showing a bare error string.

Contract:

- Schema failures produce ``detail = {"summary": ..., "errors": [...]}``.
- Each error carries ``path`` (dot-joined loc), ``message``, ``target_index``
  (integer when the failure is on a specific target in ``targets``),
  and ``type`` (Pydantic error type or ``"capability_mismatch"``).
- Capability catalog failures ride the same shape so the frontend has
  one code path for both.

Server is authoritative — the client-side capability catalog mirror
at ``apps/web/src/lib/gatewayCapabilityCatalog.ts`` is a UX hint only.
This contract is what publishes stand or fall on.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException


def _validate(working_copy: dict) -> None:
    from app.routers.gateway_profiles_v2 import _validate_working_copy
    _validate_working_copy(working_copy)


def _err_body(exc: HTTPException) -> dict:
    """FastAPI serializes HTTPException detail as-is; assert it's the
    structured dict shape rather than a stringified error."""
    assert isinstance(exc.detail, dict), (
        f"detail must be structured dict, got {type(exc.detail).__name__}"
    )
    assert "summary" in exc.detail
    assert isinstance(exc.detail["errors"], list)
    return exc.detail


def test_schema_error_reports_target_index_for_bad_credential_ref():
    """Bad credential_ref on target[2]. Response must carry
    ``target_index=2`` so the editor knows which row to highlight."""
    with pytest.raises(HTTPException) as excinfo:
        _validate({
            "name": "p",
            "model_alias": "coding",
            "accepts": ["anthropic_messages"],
            "targets": [
                {"id": "a", "transport": "native_http", "provider": "anthropic",
                 "model": "claude-sonnet-4-6",
                 "credential_ref": "vault://11111111-1111-1111-1111-111111111111/anthropic"},
                {"id": "b", "transport": "native_http", "provider": "anthropic",
                 "model": "claude-sonnet-4-6",
                 "credential_ref": "vault://11111111-1111-1111-1111-111111111111/anthropic"},
                {"id": "c", "transport": "native_http", "provider": "anthropic",
                 "model": "claude-sonnet-4-6",
                 "credential_ref": "vault:not-a-ref"},
            ],
        })
    assert excinfo.value.status_code == 400
    detail = _err_body(excinfo.value)
    # Find the error pointing at target[2].
    idx2_errs = [e for e in detail["errors"] if e["target_index"] == 2]
    assert idx2_errs, f"expected error on target_index=2, got: {detail['errors']}"
    err = idx2_errs[0]
    assert "credential_ref" in err["path"]
    assert err["type"] != "capability_mismatch"


def test_capability_mismatch_rides_the_same_error_shape():
    """A published-catalog rejection returns the same ``detail`` shape as
    a Pydantic failure so the UI has one rendering path for both."""
    with pytest.raises(HTTPException) as excinfo:
        _validate({
            "name": "p",
            "model_alias": "coding",
            "accepts": ["anthropic_messages"],
            "targets": [
                # OpenRouter passthrough for Anthropic Messages is not
                # certified even in PR 5 (OpenRouter is chat-completions
                # only). Publish must reject.
                {"id": "via-openrouter", "transport": "http_passthrough",
                 "integration": "openrouter",
                 "model": "anthropic/claude-sonnet",
                 "credential_ref": "vault://11111111-1111-1111-1111-111111111111/openrouter"},
            ],
        })
    assert excinfo.value.status_code == 400
    detail = _err_body(excinfo.value)
    assert detail["summary"] == "capability check failed"
    assert len(detail["errors"]) == 1
    err = detail["errors"][0]
    assert err["type"] == "capability_mismatch"
    # Full CapabilityMismatch message name-drops the target + catalog
    # version — must survive into the ``message`` field intact.
    assert "via-openrouter" in err["message"]
    assert "anthropic_messages" in err["message"]


def test_discriminated_union_noise_filtered_to_declared_transport():
    """Pydantic's discriminated-union validation walks every variant
    when the transport-tagged variant fails a field check. That
    produces N×3 error blobs (e.g. ``targets.0.NativeHTTPTarget.credential_ref``
    AND ``targets.0.LiteLLMSDKTarget.credential_ref`` AND
    ``targets.0.HTTPPassthroughTarget.credential_ref``) for a single
    logical error — real user-reported gotcha ("14 errors" for two
    targets with empty credential_ref).

    The filter should keep ONLY the errors whose variant matches the
    target's declared ``transport``, and strip the variant class name
    from the path so the UI sees ``targets.0.credential_ref`` cleanly.
    """
    with pytest.raises(HTTPException) as excinfo:
        _validate({
            "name": "p",
            "model_alias": "coding",
            "accepts": ["anthropic_messages"],
            "targets": [
                # User's declared transport is litellm_sdk. Real problem:
                # credential_ref is empty. Pydantic will emit the same
                # ``string_too_short`` error under every union variant.
                {"id": "primary", "transport": "litellm_sdk",
                 "provider": "anthropic",
                 "model": "claude-sonnet-4-6",
                 "credential_ref": ""},
                {"id": "fallback", "transport": "litellm_sdk",
                 "provider": "anthropic",
                 "model": "claude-haiku-4-5-20251001",
                 "credential_ref": ""},
            ],
        })
    detail = _err_body(excinfo.value)
    # No path should carry a union-variant class name — filtered out
    # or stripped.
    for variant_name in ("NativeHTTPTarget", "LiteLLMSDKTarget", "HTTPPassthroughTarget"):
        assert not any(variant_name in e["path"] for e in detail["errors"]), (
            f"union variant name {variant_name} leaked into paths: "
            f"{[e['path'] for e in detail['errors']]}"
        )
    # Both targets must have their credential_ref error reported
    # exactly once — the whole point of the filter.
    per_target = {0: 0, 1: 0}
    for e in detail["errors"]:
        if e["target_index"] in per_target and "credential_ref" in e["path"]:
            per_target[e["target_index"]] += 1
    assert per_target == {0: 1, 1: 1}, (
        f"expected one credential_ref error per target after filter, "
        f"got {per_target} across errors={detail['errors']}"
    )


def test_schema_error_at_profile_root_has_no_target_index():
    """Errors on profile-level fields (empty targets, unknown operation)
    have ``target_index=None``; the UI should surface them as a
    top-level error banner, not attached to a row."""
    with pytest.raises(HTTPException) as excinfo:
        _validate({
            "name": "p",
            "model_alias": "coding",
            "accepts": ["not_a_real_operation"],
            "targets": [
                {"id": "a", "transport": "native_http", "provider": "anthropic",
                 "model": "claude-sonnet-4-6",
                 "credential_ref": "vault://11111111-1111-1111-1111-111111111111/anthropic"},
            ],
        })
    detail = _err_body(excinfo.value)
    # At least one error must be on ``accepts`` with no target_index.
    accept_errors = [
        e for e in detail["errors"]
        if e["path"].startswith("accepts")
    ]
    assert accept_errors, f"expected error on accepts, got: {detail['errors']}"
    assert all(e["target_index"] is None for e in accept_errors)
