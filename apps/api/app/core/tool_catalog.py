"""Packaged tool metadata shared with CLI and web; not authorization."""
import json
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))
if CATALOG.get("schema_version") != 1:
    raise ValueError("Unsupported tool catalog version")
TOOLS = {tool["id"]: tool for tool in CATALOG["tools"]}
