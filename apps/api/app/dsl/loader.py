"""
YAML <-> runtime graph translation.

The executor (``app/runtime/executor.py``) consumes a graph dict of the shape:

    {
      "nodes": [
        {"id": ..., "type": "block", "position": {x, y}, "data": {...}},
        ...
      ],
      "edges": [
        {"id": ..., "source": ..., "target": ..., "sourceHandle": "pass" | None},
        ...
      ]
    }

This module converts the validated DSL ``Workflow`` model into that shape.
The executor stays untouched: YAML is layered *over* the runtime, not into it.
"""
from __future__ import annotations

import copy
import functools
import re
from pathlib import Path
from typing import Any

import yaml

from app.dsl.schema import (
    Workflow,
    WorkflowValidationError,
)

# Re-exported for callers that import these names from this module.
from app.dsl.loader_graph import (  # noqa: E402,F401
    TRIGGER_NODE_ID,
    carry_annotations,
    graph_to_workflow,
    yaml_to_graph,
)


# ---------------------------------------------------------------------------
# YAML Schema validation (opt-in, fires only when schema_version: "1")
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _load_v1_schema() -> dict:
    """Load and cache the JSON Schema draft-07 document from v1.yaml."""
    schema_path = Path(__file__).parent / "schema" / "v1.yaml"
    with open(schema_path) as f:
        return yaml.safe_load(f)


def _validate_against_yaml_schema(data: dict) -> None:
    """Validate *data* against the v1 JSON Schema if schema_version == "1".

    Only fires when the playbook opts in via ``schema_version: "1"``.
    Raises WorkflowValidationError on any schema violation so callers see a
    consistent exception type regardless of the validation layer that caught it.
    """
    if data.get("schema_version") != "1":
        return  # opt-in only — existing playbooks are unaffected

    import jsonschema  # deferred import; only needed for schema_version: "1" playbooks

    schema = _load_v1_schema()
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as e:
        raise WorkflowValidationError(
            f"Playbook schema validation failed: {e.message}"
        ) from e


# ---------------------------------------------------------------------------
# Registry-driven block validation
# ---------------------------------------------------------------------------


def _validate_blocks_against_registry(blocks: dict) -> None:
    """Check block configs against the schema registry for types not covered by Pydantic."""
    from app.runtime.block_schemas import validate_yaml_block

    for block_id, block_data in blocks.items():
        if not isinstance(block_data, dict):
            continue
        block_type = block_data.get("type", "")
        missing = validate_yaml_block(block_type, block_data)
        if missing:
            raise WorkflowValidationError(
                f"Block '{block_id}' ({block_type}) is missing required fields: "
                + ", ".join(missing)
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_workflow_yaml(yaml_text: str, base_dir: Path | None = None) -> Workflow:
    """Parse + validate a YAML document. Raises WorkflowValidationError on failure.

    If *base_dir* is supplied and the document contains an ``extends:`` key, the
    base file is resolved from *base_dir* and all ``$use`` / ``{{$snippet:}}``
    references are expanded before Pydantic validation.  When *base_dir* is None
    (community submissions), ``extends:`` is rejected outright.
    """
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise WorkflowValidationError(f"invalid YAML: {e}") from e

    if not isinstance(data, dict):
        raise WorkflowValidationError(
            "workflow YAML must be a mapping at the top level"
        )

    data = _restore_keyword_keys(data)

    # Resolve extends: before Pydantic validation so the model never sees it.
    if "extends" in data:
        if base_dir is None:
            raise WorkflowValidationError(
                "extends: not supported for community submissions"
            )
        data = _resolve_extends(data, base_dir)

    # JSON Schema validation (opt-in — only runs when schema_version: "1")
    _validate_against_yaml_schema(data)

    try:
        workflow = Workflow.model_validate(data)
    except Exception as e:  # pydantic.ValidationError or our own ValueError
        raise WorkflowValidationError(str(e)) from e

    # Registry-driven validation for block types not covered by Pydantic
    _validate_blocks_against_registry(data.get("blocks") or {})

    return workflow


# ---------------------------------------------------------------------------
# extends: resolution helpers
# ---------------------------------------------------------------------------

def _resolve_extends(data: dict, base_dir: Path) -> dict:
    """Resolve ``extends:`` in *data* in-place and return the expanded dict.

    Steps:
    1. Load and validate the base file (must have ``kind: base``).
    2. For each block that has a ``$use`` key, merge base block fields as
       defaults with the child block's fields winning on conflict.
    3. Walk all string values in block descriptions and replace
       ``{{$snippet: name}}`` with the raw snippet text.
    4. Delete ``extends`` from the returned dict.
    """
    base_name: str = data["extends"]
    base_path = base_dir / f"{base_name}.yaml"

    try:
        base_text = base_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise WorkflowValidationError(
            f"extends: base file not found: {base_path}"
        )

    try:
        base_data = yaml.safe_load(base_text)
    except yaml.YAMLError as e:
        raise WorkflowValidationError(f"extends: invalid YAML in base file: {e}") from e

    if not isinstance(base_data, dict) or base_data.get("kind") != "base":
        raise WorkflowValidationError(
            f"extends: '{base_name}' is not a base file (missing kind: base)"
        )

    base_snippets: dict[str, str] = base_data.get("snippets") or {}
    base_blocks: dict[str, dict] = base_data.get("blocks") or {}

    # Work on a shallow copy so we don't mutate the caller's dict.
    data = dict(data)

    # --- Step 2: resolve $use in blocks ------------------------------------
    if "blocks" in data and isinstance(data["blocks"], dict):
        resolved_blocks: dict[str, Any] = {}
        for block_id, block in data["blocks"].items():
            if not isinstance(block, dict):
                resolved_blocks[block_id] = block
                continue

            use_ref = block.get("$use")
            if use_ref is None:
                resolved_blocks[block_id] = block
                continue

            # Strip the "base-autopilot." (or any "<base-name>.") prefix.
            prefix = f"{base_name}."
            template_key = use_ref[len(prefix):] if use_ref.startswith(prefix) else use_ref

            if template_key not in base_blocks:
                raise WorkflowValidationError(
                    f"extends: unknown block template '{use_ref}' in {base_name}"
                )

            # Deep-merge: base fields as defaults, child fields WIN.
            merged = copy.deepcopy(base_blocks[template_key])
            child_fields = {k: v for k, v in block.items() if k != "$use"}
            merged.update(child_fields)
            merged["is_readonly"] = True  # mark so canvas shows read-only banner
            resolved_blocks[block_id] = merged

        data["blocks"] = resolved_blocks

    # --- Step 3: inject snippets in string values -------------------------
    def _snippet_replacer(m: re.Match) -> str:
        name = m.group(1)
        if name not in base_snippets:
            raise WorkflowValidationError(
                f"unknown snippet '{name}' in {base_name}"
            )
        return base_snippets[name]

    _SNIPPET_RE = re.compile(r'\{\{\$snippet:\s*(\w+)\s*\}\}')

    def _walk_strings(obj: Any) -> Any:
        if isinstance(obj, str):
            return _SNIPPET_RE.sub(_snippet_replacer, obj)
        if isinstance(obj, dict):
            return {k: _walk_strings(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk_strings(item) for item in obj]
        return obj

    if "blocks" in data:
        data["blocks"] = _walk_strings(data["blocks"])

    # --- Step 4: strip extends key ----------------------------------------
    data.pop("extends")
    return data


# YAML 1.1 (which PyYAML still implements) coerces the bare tokens ``on``,
# ``off``, ``yes`` and ``no`` to booleans/None when they appear as scalars —
# including as mapping keys. That makes ``on:`` parse as ``True:``, which
# obviously doesn't round-trip through Pydantic's string-keyed validators.
# GitHub Actions hits the exact same problem. We restore the intended string
# keys at the top level here so authors don't have to quote ``"on":``.
_KEYWORD_KEY_RESTORATIONS = {True: "on", False: "off", None: "null"}


def _restore_keyword_keys(data: dict) -> dict:
    fixed: dict = {}
    for k, v in data.items():
        if k in _KEYWORD_KEY_RESTORATIONS:
            fixed[_KEYWORD_KEY_RESTORATIONS[k]] = v
        else:
            fixed[k] = v
    return fixed


def workflow_to_yaml(workflow: Workflow) -> str:
    """Round-trip a validated Workflow back to YAML (used by API GET)."""
    data = workflow.model_dump(by_alias=True, exclude_none=True, exclude_defaults=False)
    # Drop empty containers so the output stays human-readable.
    for k in ("params", "cleanup"):
        if data.get(k) == {}:
            data.pop(k)
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
