"""Parity + drilldown checks for the batch-1 read tools (8 domains, 16 tools).

Guards against drift between:
- Executor `_tool_*` methods
- `ToolDef` registrations in `app/tools/registrations/lens.py`
- `TOOLS` schema list seen by the LLM
- `_build_drilldown` routes seen by the UI

Isolated (no DB) — behavior tests live under each domain's owned suite.
"""
from __future__ import annotations

BATCH1_TOOLS = (
    # #1287 approvals
    "list_pending_approvals",
    "get_approval",
    # #1288 packs
    "list_installed_packs",
    "browse_marketplace",
    "get_pack_details",
    # #1289 integrations
    "list_integrations",
    "get_integration_status",
    # #1290 team
    "list_members",
    "get_member",
    # #1291 audit
    "get_audit_events",
    "search_audit_log",
    # #1292 projects
    "list_projects",
    "get_project",
    # #1293 alerts
    "list_alerts",
    "get_alert",
    # #1294 logs
    "list_run_events",
)


def test_registrations_expose_all_batch1_tools():
    from app.tools.registrations import lens
    from app.tools.registry import default_registry
    lens.register(replace=True)
    names = {t.name for t in default_registry._tools.values() if "lens" in t.tags}
    missing = [n for n in BATCH1_TOOLS if n not in names]
    assert not missing, f"Not registered: {missing}"


def test_chat_TOOLS_exposes_all_batch1_tools():
    from app.modules.glens.routers import chat
    names = {t["name"] for t in chat.TOOLS}
    missing = [n for n in BATCH1_TOOLS if n not in names]
    assert not missing, f"Not in chat.TOOLS: {missing}"


def test_drilldown_routes_per_domain():
    from app.modules.glens.routers import chat
    cases = [
        # (tool_name, args, expected_url_or_prefix)
        (("list_pending_approvals", {}), "/theguard/approvals"),
        (("list_pending_approvals", {"status": "approved"}), "/theguard/approvals?status=approved"),
        (("get_approval", {"id": "abc"}), "/theguard/approvals"),
        (("list_installed_packs", {}), "/packs"),
        (("get_pack_details", {"slug": "soc2"}), "/packs/soc2"),
        (("list_integrations", {}), "/integrations"),
        (("list_members", {}), "/theguard/team"),
        (("list_members", {"role": "admin"}), "/theguard/team?role=admin"),
        (("get_audit_events", {}), "/audit"),
        (("search_audit_log", {"q": "invite"}), "/audit"),
        (("list_projects", {}), "/projects"),
        (("get_project", {"id_or_slug": "foo"}), "/projects/foo"),
        (("list_alerts", {}), "/observability/alerts"),
        (("list_alerts", {"severity": "error"}), "/observability/alerts?severity=error"),
        (("list_run_events", {"run_id": "r1"}), "/runs/r1"),
    ]
    for call, expected in cases:
        got = chat._build_drilldown([call])
        assert got == expected, f"{call} → expected {expected}, got {got}"
