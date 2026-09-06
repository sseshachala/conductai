"""Lens tool registrations — capabilities (self-introspection).

Answers "what can you do?" / "what tools do you have for X?" without the
user having to grep the codebase. Introspects the live default_registry
at call time so the answer stays truthful as tools land or ship.
"""
from __future__ import annotations

from app.tools.types import ToolDef
from app.tools.registrations.lens._shared import _READ_ONLY, _LENS_TAGS


def list_capabilities(ctx, domain: str | None = None) -> dict:
    """Introspect the live Lens tool registry.

    Args:
      domain: optional case-insensitive substring; matches any of the
        tool's name, description, or non-'lens' tags.
    """
    from app.tools.registry import default_registry

    tools = default_registry.list(tag="lens")
    if domain:
        needle = domain.strip().lower()
        def _matches(t):
            hay = " ".join([
                t.name.lower(),
                (t.description or "").lower(),
                " ".join(x for x in t.tags if x != "lens").lower(),
            ])
            return needle in hay
        tools = [t for t in tools if _matches(t)]

    items = [
        {
            "name": t.name,
            "description": (t.description or "").split("\n", 1)[0][:200],
            "tags": [x for x in t.tags if x != "lens"],
            "read_only": bool(t.annotations.read_only),
        }
        for t in tools
    ]
    items.sort(key=lambda x: x["name"])
    return {"count": len(items), "domain": domain, "tools": items}


TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_capabilities",
        description=(
            "List Lens's own tool capabilities. Answers 'what can you do?' / "
            "'what tools do you have for X?'. Optional `domain` filters by "
            "case-insensitive substring against tool name/description/tags."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Optional substring filter (e.g. 'runs', 'compliance', 'agent').",
                },
            },
            "required": [],
        },
        impl=list_capabilities,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
