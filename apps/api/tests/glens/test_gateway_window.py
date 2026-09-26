"""Receipt-first Gateway answers, using real SQL and workspace permissions."""
import json
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.modules.glens.platform_evidence import PlatformEvidenceQuery
from app.modules.glens.evidence_explanation import answer_from_result, refresh_saved_evidence
from tests.glens.test_platform_evidence import platform, read  # noqa: F401
from tests.glens.test_trial_accounting import accounting, ALICE, BOB  # noqa: F401
from tests.glens.test_trial_evidence import data, WS, OTHER, NOW  # noqa: F401


@pytest.fixture
def gateway(platform):
    db, activity, receipt, _ = platform
    for ddl in [
        "ALTER TABLE llm_attempt_receipts ADD COLUMN source TEXT",
        "ALTER TABLE llm_attempt_receipts ADD COLUMN developer_external_id TEXT",
        "ALTER TABLE llm_attempt_receipts ADD COLUMN finalized_at TIMESTAMP",
    ]:
        db.execute(text(ddl))
    def add(source="gateway", user="alice", when=NOW, identity=ALICE, **kwargs):
        event = activity(user=user, identity=identity)
        row = receipt(event, **kwargs)
        db.execute(text("UPDATE llm_attempt_receipts SET source=:s, developer_external_id=:u, finalized_at=:t WHERE id=:id"),
                   {"s": source, "u": user, "t": when.strftime("%Y-%m-%d %H:%M:%S.%f"), "id": row["id"].hex})
        return event, row
    return db, add


def result(db, **kwargs):
    return read(db, surface="gateway", intent=kwargs.pop("intent", "spend"), **kwargs)


def answer(value):
    return answer_from_result(value.model_dump_json(), str(WS), "get_platform_evidence")


def test_spend_totals_are_not_limited_to_display_page(gateway):
    db, add = gateway
    for _ in range(3):
        add()
    value = result(db, limit=1)
    assert value.gateway_window.attempt_count == 3
    assert len(value.gateway_window.attempts) == 1
    assert value.gateway_window.cost_microdollars == 3600
    rendered, saved = answer(value)
    assert "$0.003600 USD" in rendered
    assert "Recorded Conduct Activity" not in rendered
    assert saved["intent"] == "spend"
    assert "/logs/guard?id=" in rendered


def test_tenant_actor_surface_and_exclusive_end(gateway):
    db, add = gateway
    add()
    add(user="bob", identity=BOB)
    add(workspace_id=OTHER)
    add(source="lens")
    add(when=NOW + timedelta(hours=1))
    add(when=NOW - timedelta(hours=2))
    assert result(db).gateway_window.attempt_count == 1


@pytest.mark.parametrize("changes", [
    {"usage_completeness": "partial"}, {"pricing_completeness": "unpriced"},
    {"calculated_cost_microdollars": None}, {"currency": "EUR"}, {"contract_version": 999},
])
def test_incomplete_cost_is_not_silently_counted(gateway, changes):
    db, add = gateway
    add()
    add(**changes)
    value = result(db)
    assert value.gateway_window.cost_microdollars == 1200
    assert value.gateway_window.priced_count == 1
    assert "partial recorded subtotal" in answer(value)[0]


def test_empty_is_not_zero_and_reported_zero_is_zero(gateway):
    db, add = gateway
    assert "**unavailable**" in answer(result(db))[0]
    add(calculated_cost_microdollars=0)
    assert "**$0.000000 USD**" in answer(result(db))[0]


def test_failures_are_attempt_outcomes_not_policy_decisions(gateway):
    db, add = gateway
    event, _ = add(execution_outcome="failed")
    add()
    value = result(db, intent="failures")
    assert value.gateway_window.attempt_count == 1
    assert value.gateway_window.attempts[0].event_id == event["id"]
    assert value.gateway_window.cost_microdollars is None
    assert "later fallback may have succeeded" in answer(value)[0]


def test_spend_is_reauthorized_on_session_reload(gateway):
    db, add = gateway
    add()
    _, saved = answer(result(db))
    db.execute(text("DELETE FROM role_permissions WHERE role_id=1 AND permission_id=3"))
    assert result(db).status == "denied"
    assert result(db, intent="failures").status == "empty"
    refreshed = refresh_saved_evidence(json.dumps({"evidence_tool": "get_platform_evidence", "evidence_query": saved}), db, str(WS), "alice")
    assert "$" not in refreshed and "do not have access" in refreshed


def test_today_is_server_resolved_and_saved_dates_stay_fixed():
    query = PlatformEvidenceQuery(surface="gateway", intent="spend", period="today")
    assert query.since.hour == query.since.minute == query.since.second == 0
    assert query.until - query.since == timedelta(days=1)
    restored = PlatformEvidenceQuery.model_validate(query.model_dump(mode="json"))
    assert restored.since == query.since and restored.until == query.until


def test_storage_failure_does_not_look_like_zero(gateway):
    db, _ = gateway
    db.execute(text("DROP TABLE llm_attempt_receipts"))
    value = result(db)
    assert value.status == "unavailable" and value.gateway_window is None


def test_owned_identity_and_external_developer_attribution(gateway):
    db, add = gateway
    add(user=None)
    add(user="alice", identity=BOB)
    add(user="bob", identity=BOB)
    assert result(db).gateway_window.attempt_count == 2


def test_workspace_scope_needs_both_activity_and_spend(gateway):
    db, add = gateway
    add(user="bob", identity=BOB)
    assert result(db, scope="workspace").status == "denied"
    value = result(db, user="admin", scope="workspace")
    assert value.gateway_window.attempt_count == 1
    db.execute(text("DELETE FROM role_permissions WHERE role_id=2 AND permission_id=4"))
    assert result(db, user="admin", scope="workspace").status == "denied"


@pytest.mark.parametrize("filters", [{"surface": "all"}, {"decision": "blocked"}, {"exact_resource": True}])
def test_spend_cannot_silently_ignore_activity_filters(filters):
    with pytest.raises(ValueError):
        PlatformEvidenceQuery(**{"surface": "gateway", "intent": "spend", **filters})


def test_registered_tool_returns_receipt_answer(gateway, monkeypatch):
    from types import SimpleNamespace
    from app.tools.registrations.lens.platform_evidence import get_platform_evidence, TOOLS
    db, add = gateway
    add()
    monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)
    monkeypatch.setattr("app.core.workspace_context.set_workspace_rls", lambda *args: None)
    value = get_platform_evidence(SimpleNamespace(workspace_id=str(WS), clerk_user_id="alice"),
                                  surface="gateway", intent="spend", since=NOW - timedelta(hours=1),
                                  until=NOW + timedelta(hours=1))
    rendered, saved = answer_from_result(json.dumps(value), str(WS), "get_platform_evidence")
    assert "$0.001200 USD" in rendered
    assert saved["intent"] == "spend"
    assert "intent" in TOOLS[0].input_schema["properties"]
