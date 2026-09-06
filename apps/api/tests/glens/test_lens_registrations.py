"""Parity checks for the Lens tool registration surface.

Guards against drift between Executor methods, ToolDef registrations, TOOLS
schema seen by the LLM, and drilldown routes seen by the UI. If any of the
four falls out of sync, the LLM either can't call a tool or answers correctly
but drilldown lands on the wrong page.
"""
from __future__ import annotations


NEW_TOOLS = (
    "list_agent_identities",
    "get_agent_identity_count",
    "get_workflow_details",
    "list_runs",
    "get_run",
)


def test_registrations_expose_all_new_tools():
    from app.tools.registrations import lens
    from app.tools.registry import default_registry

    lens.register(replace=True)
    names = {t.name for t in default_registry._tools.values() if "lens" in t.tags}
    missing = [n for n in NEW_TOOLS if n not in names]
    assert not missing, f"Not registered on default_registry: {missing}"


def test_chat_TOOLS_exposes_all_new_tools():
    from app.modules.glens.routers import chat
    names = {t["name"] for t in chat.TOOLS}
    missing = [n for n in NEW_TOOLS if n not in names]
    assert not missing, f"Not in chat.TOOLS: {missing}"


def test_drilldown_routes_agent_identity_page():
    from app.modules.glens.routers import chat
    url = chat._build_drilldown([("list_agent_identities", {})])
    assert url and url.startswith("/agent-identity"), url

    url = chat._build_drilldown([("get_agent_identity_count", {"status": "deactivated"})])
    assert url == "/agent-identity?status=deactivated", url


def test_drilldown_routes_workflow_and_run_pages():
    from app.modules.glens.routers import chat

    # get_workflow_details with workflow_id → specific workflow page
    assert chat._build_drilldown([("get_workflow_details", {"workflow_id": "wf-1"})]) == "/workflows/wf-1"

    # get_run with run_id → specific run page
    assert chat._build_drilldown([("get_run", {"run_id": "run-1"})]) == "/runs/run-1"

    # list_runs → /runs with filter querystring
    assert chat._build_drilldown([("list_runs", {"status": "failed"})]) == "/runs?status=failed"
