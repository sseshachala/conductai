"""Workflow <-> canvas graph translation (split from loader.py).

``graph_to_workflow`` turns a canvas ``{nodes, edges}`` graph into a validated
``Workflow``; ``yaml_to_graph`` lays a ``Workflow`` out as canvas nodes/edges.
``app.dsl.loader`` re-exports every public name here.
"""
from __future__ import annotations
from typing import Any
from app.dsl.schema import (
    Block,
    CleanupBlock,
    SUPPORTED_BLOCK_TYPES,
    Workflow,
    WorkflowValidationError,
)


# Synthetic id reserved for the trigger node we generate from ``on:``.
TRIGGER_NODE_ID = "_trigger"


def graph_to_workflow(
    graph: dict[str, Any],
    name: str,
    description: str | None = None,
) -> Workflow:
    """
    Reverse of ``yaml_to_graph``: rebuild a DSL ``Workflow`` from the React
    Flow ``{nodes, edges}`` shape the canvas produces.

    Two things make this non-trivial and worth doing server-side rather than
    in the canvas itself: (1) the executor's node data shape mixes block-level
    and config-level fields differently for each block type, and (2) logic
    routing uses ``sourceHandle: pass|fail`` on edges, which has to be folded
    back into the block's ``next: {pass, fail}`` dict. Putting this in Python
    keeps a single source of truth for the schema.
    """
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []

    # Index edges by source for routing reconstruction.
    out_edges: dict[str, list[dict[str, Any]]] = {}
    for e in edges:
        out_edges.setdefault(e["source"], []).append(e)

    trigger_payload: dict[str, Any] | None = None
    blocks_payload: dict[str, Any] = {}
    cleanup_payload: dict[str, Any] = {}

    for node in nodes:
        node_id = node["id"]
        data = node.get("data") or {}
        block_type = data.get("type")

        # — synthetic trigger node ----------------------------------------
        if node_id == TRIGGER_NODE_ID or block_type == "trigger":
            cfg = data.get("config") or {}
            event = cfg.get("event_type") or data.get("label") or "manual"
            # Convert underscore form back to dot-notation for the YAML on: key
            # Only applies to integration-prefixed events (e.g. github_issue_labeled → github.issue_labeled)
            _YAML_EVENT_MAP = {"github_issue_labeled": "github.issue_labeled"}
            event_yaml_key = _YAML_EVENT_MAP.get(event, event)
            extras = {k: v for k, v in cfg.items() if k != "event_type"}
            trig: dict[str, Any] = {
                "integration": data.get("integration"),
                **extras,
            }
            entry_edges = out_edges.get(node_id, [])
            if entry_edges:
                trig["next"] = entry_edges[0]["target"]
            trigger_payload = {event_yaml_key: {k: v for k, v in trig.items() if v is not None}}
            continue

        # — cleanup blocks ------------------------------------------------
        if block_type == "cleanup":
            cleanup_payload[node_id] = _node_to_block_payload(
                data, out_edges.get(node_id, []), is_cleanup=True, block_id=node_id,
            )
            continue

        # — regular blocks ------------------------------------------------
        blocks_payload[node_id] = _node_to_block_payload(
            data, out_edges.get(node_id, []), is_cleanup=False, block_id=node_id,
        )

    document: dict[str, Any] = {"name": name, "version": 1}
    if description:
        document["description"] = description
    if trigger_payload:
        document["on"] = trigger_payload
    document["blocks"] = blocks_payload
    if cleanup_payload:
        document["cleanup"] = cleanup_payload

    # Round-trip through the validator so we never emit invalid YAML.
    try:
        return Workflow.model_validate(document)
    except Exception as e:
        raise WorkflowValidationError(str(e)) from e


def _node_to_block_payload(
    data: dict[str, Any],
    outgoing: list[dict[str, Any]],
    *,
    is_cleanup: bool,
    block_id: str | None = None,
) -> dict[str, Any]:
    """Translate one canvas-shaped node back into a DSL block dict."""
    block_type = data.get("type")
    config = (data.get("config") or {}) if isinstance(data.get("config"), dict) else {}

    payload: dict[str, Any] = {}

    # Cleanups always run as a tool action; allow the underlying type to be
    # preserved if the canvas tagged it. Default to "tool" since that's the
    # only thing cleanup currently dispatches to.
    underlying_type = data.get("__underlying_type") or block_type
    if is_cleanup:
        underlying_type = "tool"

    payload["type"] = underlying_type
    # Skip echoing the auto-generated label that yaml_to_graph injects (label
    # defaults to block_id when the author didn't set one). Anything different
    # came from the user and is worth preserving.
    label = data.get("label")
    if label and label != block_id:
        payload["label"] = label
    if data.get("description"):
        payload["description"] = data["description"]
    if data.get("integration") and block_type != "output":
        payload["integration"] = data["integration"]

    if underlying_type == "tool":
        action = config.get("action")
        if action:
            payload["action"] = action
        params = config.get("params") or {}
        if params:
            payload["params"] = params

    elif underlying_type == "brain":
        payload["mode"] = "agentic" if data.get("isAgentic") else "single"
        if data.get("custom_instructions"):
            payload["custom_instructions"] = data["custom_instructions"]
        rh = config.get("remote_host")
        if isinstance(rh, dict) and rh.get("ip_ref"):
            payload["runs_on"] = {
                "ip": rh["ip_ref"],
                "credentials_from": rh.get("credentials_from", "digitalocean"),
            }
            if rh.get("username"):
                payload["runs_on"]["username"] = rh["username"]
            if rh.get("port"):
                payload["runs_on"]["port"] = rh["port"]

    elif underlying_type == "logic":
        # Fall back to a placeholder so graph→YAML never fails on an unconfigured
        # logic block. The user can edit the condition in the YAML panel or canvas.
        payload["condition"] = config.get("condition") or "true"

    elif underlying_type == "approval":
        for k in ("channel", "slack_user", "message"):
            if config.get(k):
                payload[k] = config[k]

    elif underlying_type == "memory":
        for k in ("action", "scope", "key", "limit", "summary"):
            if config.get(k) is not None:
                payload[k] = config[k]

    elif underlying_type == "output":
        via = data.get("integration") or config.get("integration") or "slack"
        out_section: dict[str, Any] = {"via": via}
        if via in ("slack", "both") and config.get("channel"):
            out_section["slack"] = {"channel": config["channel"]}
        if via in ("email", "both") and config.get("to"):
            email_part: dict[str, Any] = {"to": config["to"]}
            if config.get("from_address"):
                email_part["from_address"] = config["from_address"]
            out_section["email"] = email_part
        payload["output"] = out_section

    # — routing -----------------------------------------------------------
    if is_cleanup:
        # Cleanup blocks never route.
        payload.pop("next", None)
    else:
        handle_edges = [e for e in outgoing if e.get("sourceHandle")]
        if handle_edges:
            payload["next"] = {e["sourceHandle"]: e["target"] for e in handle_edges}
        elif outgoing:
            # Default to the first outgoing edge — multi-target without handles
            # would be ambiguous, and our schema doesn't support fan-out today.
            payload["next"] = outgoing[0]["target"]

    return payload


def carry_annotations(graph: dict[str, Any], previous_graph: dict[str, Any] | None) -> dict[str, Any]:
    """
    Canvas annotations (sticky notes) are presentation-only and not part of the
    YAML DSL, so a version rebuilt from YAML would silently drop them. Copy the
    previous version's ``annotations`` onto the new graph. The runtime and
    compiler only read ``nodes``/``edges``, so annotations never execute.
    """
    annotations = (previous_graph or {}).get("annotations")
    return {**graph, "annotations": annotations} if annotations else graph


def yaml_to_graph(workflow: Workflow) -> dict[str, Any]:
    """
    Convert a validated workflow into the {nodes, edges} graph the executor uses.

    Positions are assigned deterministically by insertion order so cold-rendering
    a workflow from YAML produces a layout that is at least readable; the canvas
    is expected to re-run dagre / elk for final placement.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # ----- synthetic trigger node ------------------------------------------
    trigger_node = _build_trigger_node(workflow)
    if trigger_node is not None:
        nodes.append(trigger_node)

    # ----- main DAG --------------------------------------------------------
    col = 1
    for block_id, block in workflow.blocks.items():
        nodes.append(_block_to_node(block_id, block, col=col))
        col += 1

    # ----- cleanup blocks --------------------------------------------------
    for block_id, block in workflow.cleanup.items():
        nodes.append(_cleanup_to_node(block_id, block))

    # ----- edges -----------------------------------------------------------
    entry = workflow.entry_block_id()
    if trigger_node is not None and entry is not None:
        edges.append(_make_edge(TRIGGER_NODE_ID, entry))

    for block_id, block in workflow.blocks.items():
        nxt = block.next
        if nxt is None:
            continue
        if isinstance(nxt, str):
            if nxt != "end":
                edges.append(_make_edge(block_id, nxt))
        else:
            for handle, target in nxt.items():
                if target != "end":
                    edges.append(_make_edge(block_id, target, source_handle=handle))

    result: dict[str, Any] = {"nodes": nodes, "edges": edges}
    if workflow.inputs:
        # Serialize WorkflowParam → plain dict so downstream consumers (executor, frontend)
        # can read fields as JSON without Pydantic semantics.
        result["inputs_spec"] = {k: v.model_dump(exclude_none=True) for k, v in workflow.inputs.items()}
    return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _position(col: int, row: int = 0) -> dict[str, int]:
    return {"x": 80 + col * 260, "y": 80 + row * 180}


def _make_edge(source: str, target: str, source_handle: str | None = None) -> dict[str, Any]:
    edge: dict[str, Any] = {
        "id": f"e-{source}-{target}" + (f"-{source_handle}" if source_handle else ""),
        "source": source,
        "target": target,
    }
    if source_handle:
        edge["sourceHandle"] = source_handle
    return edge


def _build_trigger_node(workflow: Workflow) -> dict[str, Any] | None:
    """
    Collapse the (potentially multiple) entries under ``on:`` into a single
    synthetic trigger block. The runtime treats the first listed trigger as
    canonical — multi-trigger handling is a future extension and is intentionally
    not exposed yet.
    """
    if not workflow.triggers:
        return None

    event_name, trig = next(iter(workflow.triggers.items()))
    extras = trig.model_dump(exclude={"integration", "next"}, exclude_none=True)
    # Normalise dot-notation YAML keys (e.g. "github.issue_labeled") to the
    # underscore form the UI dropdown expects ("github_issue_labeled").
    event_type = event_name.replace(".", "_")

    return {
        "id": TRIGGER_NODE_ID,
        "type": "block",
        "position": _position(col=0),
        "data": {
            "type": "trigger",
            "label": event_type,
            "integration": trig.integration,
            "description": event_type,
            "config": {"event_type": event_type, **extras},
        },
    }


def _block_to_node(block_id: str, block: Block, col: int) -> dict[str, Any]:
    """Map a typed Block to the node shape the executor consumes."""
    data: dict[str, Any] = {
        "type": block.type,
        "label": block.label or block_id,
        "is_readonly": block.is_readonly,
    }
    if block.description:
        data["description"] = block.description
    if block.integration:
        data["integration"] = block.integration

    config: dict[str, Any] = {}

    # — iteration / loop fields (#565) —
    if block.for_each:
        config["for_each"] = block.for_each
        config["item_var"] = block.item_var or "item"

    # — retry config (#565) —
    if block.retry:
        config["retry"] = block.retry

    if block.type == "tool":
        # integration was possibly derived from slash-format action in _validate_by_type;
        # reflect the (possibly updated) value into data.
        if block.integration:
            data["integration"] = block.integration
        config["action"] = block.action
        # Prefer explicit params; fall back to `input` alias (#565)
        effective_params = block.params if block.params else (block.input or {})
        if effective_params:
            config["params"] = effective_params

    elif block.type == "brain":
        # The executor reads ``isAgentic`` (legacy field name from the canvas).
        data["isAgentic"] = (block.mode == "agentic")
        if block.model and "{{" not in block.model:
            data["model"] = block.model
        if block.custom_instructions:
            data["custom_instructions"] = block.custom_instructions
        # system/prompt are alternative ways to supply description/user prompt (#565)
        if block.system:
            data["description"] = block.system
        if block.prompt:
            data["prompt"] = block.prompt
        if block.allowed_tools is not None:
            config["allowed_tools"] = block.allowed_tools
        if block.runs_on:
            if isinstance(block.runs_on, str):
                # Shorthand string form: "e2b" or "modal"
                data["sandbox"] = block.runs_on
            else:
                config["remote_host"] = {
                    "ip_ref": block.runs_on.ip,
                    "credentials_from": block.runs_on.credentials_from,
                }
                if block.runs_on.username:
                    config["remote_host"]["username"] = block.runs_on.username
                if block.runs_on.port:
                    config["remote_host"]["port"] = block.runs_on.port
        if block.max_turns is not None:
            data["max_turns"] = block.max_turns
        if block.complexity is not None:
            data["complexity"] = block.complexity
        if block.sandbox:
            data["sandbox"] = block.sandbox
        # Wire execution_policy: append instructions to description, copy
        # constraints onto data so the brain block executor can read them.
        if block.execution_policy:
            ep = block.execution_policy
            ep_instructions: list[str] = ep.get("instructions") or []
            if ep_instructions:
                bullet_list = "\n".join(f"- {i}" for i in ep_instructions)
                current_desc = data.get("description") or ""
                data["description"] = (
                    f"{current_desc}\n\nExecution policy instructions:\n{bullet_list}".strip()
                )
            ep_constraints: dict = ep.get("constraints") or {}
            for field in ("rollback_on_failure", "require_tests_pass", "max_retries", "max_cost_usd"):
                if field in ep_constraints:
                    data[field] = ep_constraints[field]

    elif block.type == "memory":
        if block.action:
            config["action"] = block.action
        if block.scope:
            config["scope"] = block.scope
        if block.key:
            config["key"] = block.key
        if block.limit is not None:
            config["limit"] = str(block.limit)
        if block.summary:
            config["summary"] = block.summary

    elif block.type == "logic":
        config["condition"] = block.condition

    elif block.type == "approval":
        if block.channel:
            config["channel"] = block.channel
        if block.slack_user:
            config["slack_user"] = block.slack_user
        if block.message:
            config["message"] = block.message

    elif block.type == "mcp":
        # Pass the full config dict through to the executor.
        # ``inputs`` is the YAML-native alias for ``params`` in MCP blocks.
        mcp_cfg = dict(block.config or {})
        if "inputs" in mcp_cfg:
            mcp_cfg["params"] = mcp_cfg.pop("inputs")
        # Top-level credential_key / tool_name shadow config entries if set
        if block.credential_key:
            mcp_cfg["credential_key"] = block.credential_key
        if block.tool_name:
            mcp_cfg["tool_name"] = block.tool_name
        config.update(mcp_cfg)

    elif block.type == "output":
        if block.output is not None:
            out = block.output
            data["integration"] = out.via
            config["integration"] = out.via
            if out.slack:
                config["channel"] = out.slack.channel
                if out.slack.approval:
                    config["approval"] = True
            if out.email:
                config["to"] = out.email.to
                if out.email.from_address:
                    config["from_address"] = out.email.from_address
        elif block.channels and block.template:
            # Shorthand channels + template (#565)
            via = block.channels[0] if block.channels else "slack"
            data["integration"] = via
            config["integration"] = via
            config["template"] = block.template
            if len(block.channels) > 1:
                config["channels"] = block.channels

    if config:
        data["config"] = config

    return {
        "id": block_id,
        "type": "block",
        "position": _position(col=col),
        "data": data,
    }


def _cleanup_to_node(block_id: str, block: CleanupBlock) -> dict[str, Any]:
    """Cleanups share the tool-block executor path; we just flag them as 'cleanup'."""
    if block.type not in SUPPORTED_BLOCK_TYPES:
        raise WorkflowValidationError(
            f"cleanup block '{block_id}' has unsupported type '{block.type}'"
        )
    # Reuse _block_to_node for shape, then override the type tag.
    node = _block_to_node(block_id, block, col=99)
    node["data"]["type"] = "cleanup"
    node["data"]["__underlying_type"] = block.type  # debug aid
    return node
