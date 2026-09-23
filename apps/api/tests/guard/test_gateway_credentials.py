from types import SimpleNamespace

from app.modules.guard.gateway_credentials import (
    parse_vault_credential_ref,
    resolve_gateway_key,
    resolve_vendor_key,
)


VAULT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def test_parse_canonical_vault_credential_ref():
    parsed = parse_vault_credential_ref(f"vault://{VAULT_ID}/anthropic")

    assert parsed is not None
    assert parsed.environment_id == VAULT_ID
    assert parsed.selector == "anthropic"


def test_parse_legacy_vault_credential_ref_keeps_external_environment_scope():
    parsed = parse_vault_credential_ref("vault://providers/anthropic")

    assert parsed is not None
    assert parsed.environment_id is None
    assert parsed.selector == "anthropic"


def test_canonical_ref_resolves_only_its_embedded_vault(monkeypatch):
    calls = []

    def _get_vault_credential(db, workspace_id, environment_id, selector):
        calls.append((workspace_id, environment_id, selector))
        return {"api_key": "secret"}

    monkeypatch.setattr(
        "app.modules.guard.gateway_credentials.get_vault_credential",
        _get_vault_credential,
    )

    key = resolve_gateway_key(
        SimpleNamespace(),
        "workspace-1",
        f"vault://{VAULT_ID}/anthropic",
        "anthropic",
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    )

    assert key == "secret"
    assert calls == [("workspace-1", VAULT_ID, "anthropic")]


def test_missing_vault_reference_does_not_search_credentials(monkeypatch):
    get_credential = lambda *args: (_ for _ in ()).throw(AssertionError("must not resolve"))
    monkeypatch.setattr(
        "app.modules.guard.gateway_credentials.get_vault_credential",
        get_credential,
    )

    assert resolve_gateway_key(SimpleNamespace(), "workspace-1", None, "openai", None) is None


def test_resolve_vendor_key_finds_first_matching_name(monkeypatch):
    monkeypatch.setattr(
        "app.modules.guard.gateway_credentials.get_vault_credential",
        lambda db, ws, env, sel: {
            "HELICONE_API_KEY": "sk-hel",
            "OPENAI_API_KEY":   "sk-openai",
        },
    )
    key = resolve_vendor_key(
        SimpleNamespace(), "workspace-1",
        f"vault://{VAULT_ID}/helicone",
        ("OPENAI_API_KEY", "openai_api_key"),
        None,
    )
    assert key == "sk-openai"


def test_resolve_vendor_key_returns_none_when_no_candidates_match(monkeypatch):
    monkeypatch.setattr(
        "app.modules.guard.gateway_credentials.get_vault_credential",
        lambda db, ws, env, sel: {"HELICONE_API_KEY": "sk-hel"},
    )
    key = resolve_vendor_key(
        SimpleNamespace(), "workspace-1",
        f"vault://{VAULT_ID}/helicone",
        ("ANTHROPIC_API_KEY",),
        None,
    )
    assert key is None


def test_helicone_primary_key_uses_shared_alias(monkeypatch):
    """PR 5 review — helicone_openai / helicone_anthropic both look up
    ``HELICONE_API_KEY`` from the shared vault entry. Independent of
    PR 3's alias table so this branch works standalone."""
    monkeypatch.setattr(
        "app.modules.guard.gateway_credentials.get_vault_credential",
        lambda db, ws, env, sel: {"HELICONE_API_KEY": "sk-hel"},
    )
    for provider in ("helicone_openai", "helicone_anthropic"):
        key = resolve_gateway_key(
            SimpleNamespace(), "workspace-1",
            f"vault://{VAULT_ID}/helicone",
            provider,
            None,
        )
        assert key == "sk-hel", provider
