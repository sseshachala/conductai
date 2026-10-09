"""#2385 — Lens `export_audit_log` read tool + delivery of its result to the chat `done` event."""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.auth import get_user_id, get_workspace_id
from app.core.database import get_db
from app.main import app
from app.modules.guard.models import GuardAuditEvent
from tests.test_audit_export import WS, env, sqlite_table  # noqa: F401  (fixtures)


class _Ctx:
    workspace_id = WS
    clerk_user_id = "user_1"


@pytest.fixture
def lens_env(env):  # noqa: F811
    _, Session = env
    with patch("app.core.database.SessionLocal", Session), \
         patch("app.core.workspace_context.set_workspace_rls", lambda *a: None), \
         patch("app.core.auth.check_permission", return_value="security") as perm:
        yield Session, perm


def test_lens_tool_result_shape_is_exact(lens_env):
    from urllib.parse import parse_qs, urlsplit
    from app.tools.registrations.lens.audit_export import export_audit_log
    Session, perm = lens_env
    res = export_audit_log(_Ctx(), since="2026-09-01T11:00:00Z", until="2026-09-01T13:00:00Z",
                           decision=["block"], tool=None)
    blocked = Session().query(GuardAuditEvent).filter_by(
        workspace_id=uuid.UUID(WS), decision="blocked").one()
    assert list(res) == ["kind", "row_count", "since", "until", "format", "capped", "cap",
                         "head_hash", "tail_hash", "download_path", "filtered", "verify_hint"]
    assert res["filtered"] is True and "--allow-gaps" in res["verify_hint"]
    assert res["kind"] == "audit_export" and res["row_count"] == 1 and res["capped"] is False
    assert res["cap"] == 100_000 and res["format"] == "ndjson"
    assert res["head_hash"] == res["tail_hash"] == blocked.entry_hash
    assert res["since"] == "2026-09-01T11:00:00+00:00"
    url = urlsplit(res["download_path"])
    assert url.path == "/guard/events/export" and "+" not in url.query  # url-encoded
    q = parse_qs(url.query)
    assert q["since"] == [res["since"]] and q["format"] == ["ndjson"]
    assert set(q["decision"]) == {"block", "blocked"}
    assert perm.call_args.kwargs["permission"] == "platform.audit_log.view"


def test_lens_tool_full_range_hashes_and_count(lens_env):
    from app.tools.registrations.lens.audit_export import export_audit_log
    Session, _ = lens_env
    res = export_audit_log(_Ctx(), since="2026-09-01T11:00:00Z", until="2026-09-01T13:00:00Z", format="csv")
    rows = Session().query(GuardAuditEvent).filter_by(
        workspace_id=uuid.UUID(WS)).order_by(GuardAuditEvent.ts).all()
    assert res["row_count"] == 5 and res["format"] == "csv"
    assert res["filtered"] is False and res["verify_hint"] == "conduct audit verify <file>"
    assert (res["head_hash"], res["tail_hash"]) == (rows[0].entry_hash, rows[-1].entry_hash)


def test_lens_tool_tool_filter_is_filtered_and_description_relays_hint(lens_env):
    from app.tools.registrations.lens.audit_export import FILTERED_HINT, export_audit_log
    from app.tools.registry import default_registry
    res = export_audit_log(_Ctx(), since="2026-09-01T11:00:00Z", until="2026-09-01T13:00:00Z", tool="Bash")
    assert res["filtered"] is True and res["verify_hint"] == FILTERED_HINT
    assert "verify_hint" in default_registry.get("export_audit_log").description


def test_lens_tool_refuses_without_permission(lens_env):
    from app.tools.registrations.lens.audit_export import export_audit_log
    _, perm = lens_env
    perm.side_effect = HTTPException(status_code=403, detail="Permission denied")
    res = export_audit_log(_Ctx(), since="2026-09-01T11:00:00Z", until="2026-09-01T13:00:00Z")
    assert "platform.audit_log.view" in res["error"] and "download_path" not in res


def test_lens_tool_bad_range_and_registration(lens_env):
    from app.tools.registrations.lens.audit_export import export_audit_log
    from app.tools.registry import default_registry
    assert "error" in export_audit_log(_Ctx(), since="2026-09-02T00:00:00Z", until="2026-09-01T00:00:00Z")
    tool = default_registry.get("export_audit_log")
    assert tool.annotations.read_only and "lens" in tool.tags
    assert tool.permission == "platform.audit_log.view"
    assert "audit log" in tool.description.lower() and "export" in tool.description.lower()


# ── chat `done` event ─────────────────────────────────────────────────────────

EXPORT_RESULT = {
    "kind": "audit_export", "row_count": 5, "since": "2026-09-01T00:00:00+00:00",
    "until": "2026-09-02T00:00:00+00:00", "format": "ndjson", "capped": False, "cap": 100000,
    "head_hash": "a" * 64, "tail_hash": "b" * 64,
    "download_path": "/guard/events/export?since=x&until=y&format=ndjson",
}


@pytest.mark.parametrize("shape", ["openai", "anthropic"])
def test_extract_audit_export_both_provider_shapes(shape):
    from app.modules.glens.routers.chat import _extract_audit_export
    body = json.dumps(EXPORT_RESULT)
    msgs = ([{"role": "tool", "content": body}] if shape == "openai" else
            [{"role": "user", "content": [{"type": "tool_result", "content": body}]}])
    assert _extract_audit_export(msgs) == EXPORT_RESULT
    assert _extract_audit_export([{"role": "tool", "content": json.dumps({"error": "x"})}]) is None


def test_chat_stream_done_event_nests_audit_export_and_persists_it():
    from app.modules.glens.routers import chat
    saved = {}
    final_msgs = [{"role": "tool", "content": json.dumps(EXPORT_RESULT)}]
    fake_session = MagicMock(messages="[]", agent_identity_id=uuid.uuid4(), id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_workspace_id] = lambda: WS
    app.dependency_overrides[get_user_id] = lambda: "user_1"
    try:
        with patch.object(chat, "_get_session", return_value=fake_session), \
             patch.object(chat, "_resolve_tools",
                          return_value=(final_msgs, "Exported 5 events.", [("export_audit_log", {})])), \
             patch.object(chat, "_bg_save_session", lambda sid, msgs, title: saved.update(msgs=msgs)), \
             patch("app.modules.glens.tokens.mint_for_session", return_value="tok"):
            r = TestClient(app).post("/glens/chat/stream",
                                     json={"message": "export audit log", "session_id": str(uuid.uuid4())})
    finally:
        for dep in (get_db, get_workspace_id, get_user_id):
            app.dependency_overrides.pop(dep, None)
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    done = next(e for e in events if e["type"] == "done")
    assert done["audit_export"] == EXPORT_RESULT
    persisted = json.loads(saved["msgs"][-1]["content"])
    assert persisted["audit_export"] == EXPORT_RESULT  # rehydrates after refresh
