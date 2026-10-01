"""Bundled tool metadata; never installation verification or authorization."""
import json
from importlib.resources import files


def load_catalog():
    catalog = json.loads(files("conduct_cli").joinpath("tool_catalog.json").read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1:
        raise ValueError("Unsupported tool catalog version")
    return catalog


CATALOG = load_catalog()
TOOLS = {tool["id"]: tool for tool in CATALOG["tools"]}
