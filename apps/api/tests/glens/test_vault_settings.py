from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, JSON, MetaData, Table, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session

from app.models.environment import Environment
from app.models.workspace import Workspace
from app.models.integration import Integration
from app.modules.glens.vault_settings import PREFERENCE, save_environment, selected_environment


@pytest.fixture
def vaults():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    def projection(model, names):
        return Table(model.__tablename__, metadata, *[
            Column(name, JSON() if isinstance(model.__table__.c[name].type, (JSONB, ARRAY))
                   else model.__table__.c[name].type, primary_key=name == "id") for name in names
        ])
    # ORM queries select all columns, so preserve model shapes without FKs.
    workspaces = projection(Workspace, list(Workspace.__table__.c.keys()))
    environments = projection(Environment, list(Environment.__table__.c.keys()))
    integrations = projection(Integration, list(Integration.__table__.c.keys()))
    metadata.create_all(engine)
    ws, other, prod, foreign = [uuid4() for _ in range(4)]
    with Session(engine) as db:
        db.info["integrations"] = integrations
        db.execute(workspaces.insert(), [{"id": ws, "preferences": {"show_test_trigger": False}}, {"id": other, "preferences": {}}])
        db.execute(environments.insert(), [{"id": prod, "workspace_id": ws, "name": "Production"}, {"id": foreign, "workspace_id": other, "name": "Production"}])
        db.commit()
        yield db, ws, prod, foreign
    engine.dispose()


def test_select_production_preserves_other_preferences_and_survives_reload(vaults):
    db, ws, prod, _ = vaults
    assert selected_environment(db, ws) is None
    save_environment(db, ws, prod)
    db.expire_all()
    assert selected_environment(db, ws) == prod
    assert db.get(Workspace, ws).preferences["show_test_trigger"] is False


def test_foreign_vault_cannot_be_selected(vaults):
    db, ws, _, foreign = vaults
    with pytest.raises(HTTPException) as exc:
        save_environment(db, ws, foreign)
    assert exc.value.status_code == 404
    assert selected_environment(db, ws) is None


def test_deleted_vault_does_not_fall_back(vaults):
    db, ws, prod, _ = vaults
    save_environment(db, ws, prod)
    db.query(Environment).filter(Environment.id == prod).delete()
    db.commit()
    with pytest.raises(HTTPException) as exc:
        selected_environment(db, ws)
    assert exc.value.status_code == 404


def test_renamed_vault_still_resolves(vaults):
    db, ws, prod, _ = vaults
    save_environment(db, ws, prod)
    db.get(Environment, prod).name = "Live"
    db.commit()
    assert selected_environment(db, ws) == prod


def test_corrupt_selection_does_not_fall_back(vaults):
    db, ws, _, _ = vaults
    db.get(Workspace, ws).preferences = {PREFERENCE: "invalid"}
    db.commit()
    with pytest.raises(HTTPException) as exc:
        selected_environment(db, ws)
    assert exc.value.status_code == 409


def test_production_only_key_reaches_lens_without_default_copy(vaults, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.core.crypto import encrypt
    from app.modules.glens.routers.chat import _llm_config
    db, ws, prod, _ = vaults
    db.execute(db.info["integrations"].insert().values(id=uuid4(), workspace_id=ws,
               environment_id=prod, handle="anthropic", service="anthropic",
               encrypted_credentials=encrypt({"api_key": "production-test-only"})))
    db.commit()
    save_environment(db, ws, prod)
    monkeypatch.setattr("app.runtime.model_router.resolve_for_workspace", lambda **kw: ("anthropic", "test-model", "workspace"))
    factory = Mock()
    monkeypatch.setattr("app.runtime.llm_client.client_for", factory)
    _llm_config(SimpleNamespace(db=db, workspace_id=ws))
    factory.assert_called_once_with("anthropic", api_key="production-test-only")
