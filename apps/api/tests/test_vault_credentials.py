from types import SimpleNamespace

from app.core.credentials import get_vault_credential


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def all(self):
        return self.rows


class _Db:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        return _Query(self.rows)


def _row(handle, service, encrypted="ciphertext"):
    return SimpleNamespace(handle=handle, service=service, encrypted_credentials=encrypted)


def test_vault_credential_prefers_exact_handle(monkeypatch):
    monkeypatch.setattr("app.core.credentials.decrypt", lambda value: {"selected": value})
    db = _Db([
        _row("anthropic-production", "anthropic", "service-match"),
        _row("anthropic", "custom", "handle-match"),
    ])

    assert get_vault_credential(db, "workspace", "environment", "anthropic") == {
        "selected": "handle-match",
    }


def test_vault_credential_accepts_one_service_match(monkeypatch):
    monkeypatch.setattr("app.core.credentials.decrypt", lambda value: {"selected": value})

    assert get_vault_credential(
        _Db([_row("production-key", "openai")]),
        "workspace",
        "environment",
        "openai",
    ) == {"selected": "ciphertext"}


def test_vault_credential_rejects_ambiguous_service_match(monkeypatch):
    monkeypatch.setattr("app.core.credentials.decrypt", lambda value: {"selected": value})
    db = _Db([
        _row("openai-primary", "openai"),
        _row("openai-secondary", "openai"),
    ])

    assert get_vault_credential(db, "workspace", "environment", "openai") == {}
