"""Real row-lock regression; uses an isolated schema in a disposable database."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema


@pytest.mark.parametrize("competing_action", ["confirm", "cancel"])
def test_concurrent_lens_confirms_execute_once(monkeypatch, competing_action):
    from app.models.workspace import Workspace  # noqa: F401 - ORM FK metadata
    from app.models.run import Run  # noqa: F401 - ORM FK metadata
    from app.modules.glens.actor import helpers, registry
    from app.modules.guard.models import GuardApprovalRequest

    url = os.environ.get("LENS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("LENS_TEST_DATABASE_URL not set")
    schema = "lens_confirm_" + uuid4().hex
    admin = create_engine(url)
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}", "application_name": schema})
    metadata = MetaData()
    table = Table(GuardApprovalRequest.__tablename__, metadata, *[
        Column(c.name, c.type, primary_key=c.primary_key, nullable=not c.primary_key)
        for c in GuardApprovalRequest.__table__.columns
    ])
    with admin.begin() as conn:
        conn.execute(CreateSchema(schema))
    entered, release, second_started = Event(), Event(), Event()
    calls = []
    decisions = []
    action, workspace = uuid4(), uuid4()
    try:
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(table.insert().values(
                id=action, workspace_id=workspace, status="pending", tool_name="test_action",
                tool_input={}, requester_user_id="alice", requester_email="alice@example.test",
                timeout_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ))

        def decide(db, row, **kwargs):
            decisions.append(row.id)
            entered.set()
            assert release.wait(5)
            row.status = kwargs["decision"]
            db.commit()
            return row

        def execute(ctx, inputs):
            calls.append(ctx.workspace_id)
            return {"ok": True}

        monkeypatch.setattr(helpers, "apply_decision", decide)
        monkeypatch.setattr(helpers, "can_decide", lambda *a, **k: (True, None))
        monkeypatch.setattr(helpers, "_publish_action_event", lambda *a, **k: None)
        monkeypatch.setattr(registry, "default_action_registry", SimpleNamespace(get=lambda name: SimpleNamespace(execute=execute)))

        def confirm(second=False):
            with Session(engine) as db:
                if second:
                    second_started.set()
                try:
                    if second and competing_action == "cancel":
                        return helpers.dispatch_cancel(db, action_id=str(action), workspace_id=str(workspace),
                            clerk_user_id="alice", user_email="alice@example.test")
                    return helpers.dispatch_confirm(db, action_id=str(action), workspace_id=str(workspace),
                        clerk_user_id="alice", user_email="alice@example.test", role="admin")
                except helpers.ConfirmError as exc:
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(confirm)
            assert entered.wait(5)
            second = pool.submit(confirm, True)
            assert second_started.wait(5)
            deadline = monotonic() + 3
            blocked = False
            while monotonic() < deadline:
                with admin.connect() as conn:
                    blocked = conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE application_name=:name AND wait_event_type='Lock')"), {"name": schema}).scalar()
                if blocked:
                    break
                sleep(0.01)
            assert blocked, "The competing decision must wait on the PostgreSQL row lock"
            release.set()
            assert first.result(timeout=5)["executed"] is True
            replay = second.result(timeout=5)
            assert replay == 409 or replay.get("cached") is True
        assert len(decisions) == 1
        assert len(calls) == 1
        assert confirm()["cached"] is True
        assert len(calls) == 1
    finally:
        release.set()
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
        admin.dispose()
