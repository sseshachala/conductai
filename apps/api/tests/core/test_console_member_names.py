from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.modules.auth.console.profiles import member_names
from app.routers.projects import list_members


def member():
    return SimpleNamespace(clerk_user_id="oidc_admin", role="admin", invited_by=None,
                           joined_at=datetime.now(timezone.utc))


def test_proxy_members_use_local_names_without_clerk(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "proxy")
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = [member()]
    with patch("app.modules.auth.console.profiles.member_names", return_value={"oidc_admin": "Console admin"}) as names, \
            patch("app.routers.projects.get_clerk_user_info") as clerk:
        result = list_members("ws", "oidc_admin", "ws", "admin", db)
    assert result[0].name == "Console admin"
    assert result[0].email is None
    assert result[0].role == "admin"
    names.assert_called_once_with(db, ["oidc_admin"])
    clerk.assert_not_called()


def test_clerk_members_keep_existing_lookup(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "clerk")
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = [member()]
    with patch("app.routers.projects.get_clerk_user_info", return_value={"email": None, "name": "Clerk admin"}), \
            patch("app.modules.auth.console.profiles.member_names") as names:
        result = list_members("ws", "oidc_admin", "ws", "admin", db)
    assert result[0].name == "Clerk admin"
    names.assert_not_called()


def test_names_are_batched_and_scoped_to_issuer(monkeypatch):
    monkeypatch.setattr(settings, "console_oidc_issuer", "https://issuer.test/realm")
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(user_id="a", display_name=" Admin ", subject="sub-a", active=False),
        SimpleNamespace(user_id="b", display_name=None, subject="sub-b", active=True),
    ]
    assert member_names(db, ["a", "b"]) == {"a": "Admin", "b": "sub-b"}
    filters = db.query.return_value.filter.call_args.args
    assert filters[0].right.value == settings.console_oidc_issuer
    assert filters[1].right.value == ["a", "b"]
    db.query.assert_called_once()


def test_empty_members_do_not_query():
    db = MagicMock()
    assert member_names(db, []) == {}
    db.query.assert_not_called()


def test_workspace_mismatch_still_denied():
    from fastapi import HTTPException
    db = MagicMock()
    with pytest.raises(HTTPException) as error:
        list_members("other", "oidc_admin", "ws", "admin", db)
    assert error.value.status_code == 404
    db.execute.assert_not_called()
