"""Import + export endpoint tests for Gateway Profile v2.

Contract (per the design discussion):

- Import ALWAYS strips ``credential_ref`` on every target.
  Deliberate defense: a JSON that gets committed to a repo can't
  leak vault refs, and one file works across environments.
- Import returns ``credential_gaps`` listing every target that
  needs a vault + handle pick post-import, so callers (CLI + UI)
  can tell the admin exactly what to do next.
- Import returns ``next_url`` — an absolute link to the editor
  page for the created profile.
- ``name_override`` wins over ``working_copy.name``. Absent both →
  ``imported-profile``. Uniqueness collision → 409 with the
  structured error shape from PR #2033.
- Export prefers the active revision's snapshot; falls back to
  ``working_copy`` for pure drafts. Credentials stripped on export
  too — round-trip must produce the same shape.
"""
from __future__ import annotations

from pathlib import Path


_ROUTER_SRC = (
    Path(__file__).resolve().parents[2]
    / "app" / "routers" / "gateway_profiles_v2.py"
).read_text(encoding="utf-8")


# ─── Contract locks on the router source ──────────────────────────────


def test_import_endpoint_exists_and_uses_correct_path():
    """The endpoint must be mounted at
    ``POST /workspaces/<ws>/gateway-profiles-v2/import`` — locked in the
    design discussion so CLI + UI hit the same URL."""
    assert '"/{workspace_id}/gateway-profiles-v2/import"' in _ROUTER_SRC, (
        "Import endpoint path must match the design-locked shape. "
        "CLI + UI both target this URL; changing it silently breaks "
        "both callers."
    )
    assert "def import_profile(" in _ROUTER_SRC


def test_export_endpoint_exists_and_uses_correct_path():
    assert '"/{workspace_id}/gateway-profiles-v2/{profile_id}/export"' in _ROUTER_SRC, (
        "Export endpoint path must match the design-locked shape."
    )
    assert "def export_profile(" in _ROUTER_SRC


def test_strip_credentials_helper_is_reused_by_both_endpoints():
    """The credential-strip logic must live in one place. If
    import and export drift on strip behavior, the round-trip
    guarantee (export → import stays consistent) breaks."""
    # Both function bodies must call ``_strip_credentials``.
    import_start = _ROUTER_SRC.index("def import_profile(")
    import_end = _ROUTER_SRC.index("\n@router.", import_start)
    export_start = _ROUTER_SRC.index("def export_profile(")
    export_end = _ROUTER_SRC.index("\n@router.", export_start)
    assert "_strip_credentials(" in _ROUTER_SRC[import_start:import_end], (
        "import_profile must delegate to _strip_credentials"
    )
    assert "_strip_credentials(" in _ROUTER_SRC[export_start:export_end], (
        "export_profile must delegate to _strip_credentials — "
        "otherwise round-trip (export → import) can produce "
        "unexpectedly-populated credentials"
    )


def test_strip_credentials_is_pure_no_mutation_of_input():
    """The helper's docstring promises no mutation. Locks the deep
    copy so a future edit can't remove it silently."""
    start = _ROUTER_SRC.index("def _strip_credentials(")
    end = _ROUTER_SRC.index("\n@router.", start)
    body = _ROUTER_SRC[start:end]
    assert "json.loads(json.dumps" in body or "deepcopy" in body, (
        "_strip_credentials MUST deep-copy the input. Mutating a "
        "working_copy dict passed in from a request body would corrupt "
        "the audit trail — the same dict flows into DB write."
    )


# ─── Direct-call behavior tests ───────────────────────────────────────


def test_strip_credentials_returns_gaps_for_every_target():
    """Each target contributes exactly one ImportGap regardless of
    whether it had a credential_ref set. Both cases need action from
    the admin (either pick a vault, or accept that the stripped value
    was already empty)."""
    from app.routers.gateway_profiles_v2 import _strip_credentials

    wc = {
        "name": "test",
        "model_alias": "test",
        "accepts": ["anthropic_messages"],
        "targets": [
            {
                "id": "primary", "transport": "native_http",
                "provider": "anthropic", "model": "claude-sonnet-4-6",
                "credential_ref": "vault://env-uuid/anthropic",
            },
            {
                "id": "fallback", "transport": "native_http",
                "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
                "credential_ref": "",
            },
        ],
    }
    stripped, gaps = _strip_credentials(wc)
    assert len(gaps) == 2
    # First target had a credential → distinct reason message.
    assert "stripped" in gaps[0].reason
    assert gaps[0].target_id == "primary"
    # Second target had none → the "missing" reason.
    assert "missing" in gaps[1].reason
    # Both targets end up with empty credential_ref.
    for t in stripped["targets"]:
        assert t["credential_ref"] == ""


def test_strip_credentials_does_not_mutate_input():
    """Mutating the input dict would corrupt subsequent request
    handling. Test the promise explicitly."""
    from app.routers.gateway_profiles_v2 import _strip_credentials

    wc = {
        "name": "test",
        "targets": [{
            "id": "primary", "transport": "native_http",
            "provider": "anthropic", "model": "claude-sonnet-4-6",
            "credential_ref": "vault://original/anthropic",
        }],
    }
    _strip_credentials(wc)
    # Original dict still has the credential.
    assert wc["targets"][0]["credential_ref"] == "vault://original/anthropic"


def test_strip_credentials_handles_missing_targets_gracefully():
    """A partial working_copy without a ``targets`` key must not
    crash — import supports iterative editing, so partial JSON is
    valid input."""
    from app.routers.gateway_profiles_v2 import _strip_credentials

    stripped, gaps = _strip_credentials({"name": "partial"})
    assert stripped == {"name": "partial"}
    assert gaps == []


def test_strip_credentials_handles_non_dict_target_gracefully():
    """A malformed JSON with a non-dict entry in ``targets`` must
    not crash. Publish's shape validation will reject it later; the
    strip helper's job is to be safe for anything JSON-parseable."""
    from app.routers.gateway_profiles_v2 import _strip_credentials

    stripped, gaps = _strip_credentials({
        "targets": ["not-a-dict", {"id": "ok", "credential_ref": "vault://x/y"}],
    })
    # Only the dict target contributed a gap.
    assert len(gaps) == 1
    assert gaps[0].target_id == "ok"
    # Non-dict entry passed through untouched.
    assert stripped["targets"][0] == "not-a-dict"


# ─── R1a inline-secret rejection (import) ────────────────────────────


def test_reject_inline_secrets_finds_top_level_api_key():
    """R1a: an inline ``api_key`` on a target must fail loud on
    import. Credentials belong in Vault; an inline secret in an
    import payload is either leaked material or an admin mistake."""
    from fastapi import HTTPException as _HTTPExc
    from app.routers.gateway_profiles_v2 import _reject_inline_secrets
    import pytest as _pytest

    with _pytest.raises(_HTTPExc) as exc_info:
        _reject_inline_secrets({
            "targets": [{
                "id": "t1", "transport": "native_http",
                "provider": "anthropic", "api_key": "sk-live-shouldnothere",
            }],
        })
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["errors"][0]["type"] == "inline_secret"


def test_reject_inline_secrets_finds_nested_provider_options_key():
    """R1a: nested secret key inside ``provider_options`` must be
    caught. LiteLLM SDK profiles routinely have provider_options — an
    inline api_key at that level is the most likely leak path."""
    from fastapi import HTTPException as _HTTPExc
    from app.routers.gateway_profiles_v2 import _reject_inline_secrets
    import pytest as _pytest

    with _pytest.raises(_HTTPExc) as exc_info:
        _reject_inline_secrets({
            "targets": [{
                "id": "t1",
                "provider_options": {"api_key": "sk-live-secret"},
            }],
        })
    assert exc_info.value.status_code == 422
    assert "provider_options" in exc_info.value.detail["errors"][0]["path"]


def test_reject_inline_secrets_accepts_clean_payload():
    """Payload without any secret-shaped keys passes through — R1a
    must NOT reject clean imports."""
    from app.routers.gateway_profiles_v2 import _reject_inline_secrets

    _reject_inline_secrets({
        "targets": [{
            "id": "t1", "transport": "native_http",
            "credential_ref": "vault://env-uuid/anthropic",
            "provider_options": {"timeout_ms": 30000},
        }],
    })


def test_reject_inline_secrets_ignores_empty_string_values():
    """A key with an empty value is not a leak — an exported JSON
    could have ``credential_ref: ""`` and we must not misfire."""
    from app.routers.gateway_profiles_v2 import _reject_inline_secrets

    _reject_inline_secrets({
        "targets": [{
            "id": "t1", "api_key": "",
        }],
    })


# ─── R1b provider_options sanitisation (export) ──────────────────────


def test_strip_credentials_sanitises_provider_options_api_key():
    """R1b: a stored profile whose provider_options somehow contains
    an api_key (legacy row, direct-DB edit, etc.) must have it
    scrubbed on export — otherwise the exported JSON leaks the
    secret to whoever gets the file."""
    from app.routers.gateway_profiles_v2 import _strip_credentials

    stripped, _gaps = _strip_credentials({
        "targets": [{
            "id": "primary", "transport": "litellm_sdk",
            "provider": "openai", "model": "gpt-4",
            "credential_ref": "vault://x/y",
            "provider_options": {
                "api_key": "sk-live-shouldbescrubbed",
                "timeout_ms": 30000,
            },
        }],
    })
    opts = stripped["targets"][0]["provider_options"]
    assert "api_key" not in opts
    # Non-secret keys survive.
    assert opts["timeout_ms"] == 30000


def test_strip_credentials_sanitises_nested_authorization_header():
    """R1b: nested ``authorization`` header inside a headers dict
    must also be scrubbed. Secret keys can hide arbitrarily deep."""
    from app.routers.gateway_profiles_v2 import _strip_credentials

    stripped, _gaps = _strip_credentials({
        "targets": [{
            "id": "t1",
            "headers": {"Authorization": "Bearer sk-live-x"},
        }],
    })
    assert "Authorization" not in stripped["targets"][0]["headers"]


# ─── R3 structural validation (import) ───────────────────────────────


def test_validate_import_shape_rejects_non_dict_working_copy():
    """R3: ``working_copy`` at the top level must be an object. A
    list or scalar would crash the editor as soon as it tries to
    render fields."""
    from fastapi import HTTPException as _HTTPExc
    from app.routers.gateway_profiles_v2 import _validate_import_shape
    import pytest as _pytest

    with _pytest.raises(_HTTPExc) as exc_info:
        _validate_import_shape(["not", "an", "object"])
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["errors"][0]["type"] == "shape"


def test_validate_import_shape_rejects_dict_targets():
    """R3: ``targets`` must be a list, not a dict. Editor's target
    iteration would blow up on ``targets: {}``."""
    from fastapi import HTTPException as _HTTPExc
    from app.routers.gateway_profiles_v2 import _validate_import_shape
    import pytest as _pytest

    with _pytest.raises(_HTTPExc) as exc_info:
        _validate_import_shape({"targets": {"oops": "wrong-shape"}})
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["errors"][0]["path"] == "targets"


def test_validate_import_shape_rejects_null_target_entries():
    """R3: ``targets: [null]`` is a common paste-error shape that
    would silently corrupt the editor state."""
    from fastapi import HTTPException as _HTTPExc
    from app.routers.gateway_profiles_v2 import _validate_import_shape
    import pytest as _pytest

    with _pytest.raises(_HTTPExc) as exc_info:
        _validate_import_shape({"targets": [None]})
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["errors"][0]["target_index"] == 0


def test_validate_import_shape_accepts_partial_working_copy():
    """R3 must NOT reject valid partial payloads — import supports
    iterative editing, so missing ``targets`` is fine."""
    from app.routers.gateway_profiles_v2 import _validate_import_shape

    _validate_import_shape({"name": "partial"})
    _validate_import_shape({"name": "partial", "targets": []})


def test_import_body_shape_forbids_extra_fields():
    """The ImportProfileBody schema must ``extra='forbid'`` so a
    typoed field name (e.g. ``workingcopy`` instead of
    ``working_copy``) fails loudly at parse time instead of being
    silently dropped."""
    from app.routers.gateway_profiles_v2 import ImportProfileBody
    import pytest as _pytest

    with _pytest.raises(Exception):
        ImportProfileBody.model_validate({
            "working_copy": {"name": "x"},
            "typo_field": "surprise",
        })
