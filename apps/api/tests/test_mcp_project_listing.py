"""Run the MCP project query against the real model's schema, not mocked SQL."""
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.project import Project
from app.modules.guard.routers.mcp import _list_projects


def test_projects_use_existing_columns_and_isolate_workspace():
    engine = create_engine("sqlite://")
    Project.__table__.create(engine)
    workspace, other = uuid.uuid4(), uuid.uuid4()
    project_id = uuid.uuid4()
    try:
        with Session(engine) as db:
            db.execute(Project.__table__.insert(), [
                {"id": project_id, "workspace_id": workspace, "name": "Visible", "slug": "visible"},
                {"id": uuid.uuid4(), "workspace_id": other, "name": "Private", "slug": "private"},
            ])
            assert _list_projects(db, workspace) == [
                {"id": str(project_id), "name": "Visible", "description": None}
            ]
            assert _list_projects(db, uuid.uuid4()) == []
    finally:
        engine.dispose()


def test_projects_are_sorted_and_limited():
    engine = create_engine("sqlite://")
    Project.__table__.create(engine)
    workspace = uuid.uuid4()
    try:
        with Session(engine) as db:
            db.execute(Project.__table__.insert(), [
                {"id": uuid.uuid4(), "workspace_id": workspace, "name": f"Project {i:03}", "slug": f"p{i}"}
                for i in reversed(range(105))
            ])
            rows = _list_projects(db, workspace)
            assert len(rows) == 100
            assert [r["name"] for r in rows] == [f"Project {i:03}" for i in range(100)]
    finally:
        engine.dispose()
