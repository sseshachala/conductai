"""Per-surface tool registrations for the default ToolRegistry.

Importing this package fires each surface module's registrations as a side
effect — every tool ends up in `app.tools.registry.default_registry` before
the first MCP request. See epic #1219.

Chunk A (this file): Lens Executor tools (21). Guard MCP tools (17) land
in a follow-up chunk once the inline dispatch chain is extracted.
"""
from app.tools.registrations import lens  # noqa: F401  # side-effect
