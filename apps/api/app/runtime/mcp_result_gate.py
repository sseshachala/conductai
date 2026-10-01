"""Opt-in, fail-closed inspection for registered MCP JSON tool results."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx

from app.core.pii import redact_secrets
from app.runtime.mcp_governance import (
    MCPGovernanceDenied,
    assert_callable,
    response_mode,
)

MAX_BYTES = 1024 * 1024
MAX_NODES = 10000
MAX_DEPTH = 32


class ResultDenied(MCPGovernanceDenied):
    def __init__(self, reason):
        self.reason = reason
        super().__init__("MCP result withheld: " + reason)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ResultDenied("invalid_json")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ResultDenied("invalid_json")


async def _receive(registration, tool_name, tool_input):
    if registration.transport not in {"http", "auto"}:
        raise ResultDenied("unsupported_transport")
    request_id = str(uuid4())
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    }
    if registration.token:
        headers["Authorization"] = "Bearer " + registration.token
    body = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": tool_input},
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        async with client.stream(
            "POST", registration.url, headers=headers, json=body
        ) as response:
            if response.status_code < 200 or response.status_code >= 300:
                raise ResultDenied("upstream_error")
            if (
                response.headers.get("content-type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
                != "application/json"
            ):
                raise ResultDenied("unsupported_content_type")
            if (
                response.headers.get("content-encoding", "identity").lower()
                != "identity"
            ):
                raise ResultDenied("unsupported_encoding")
            chunks = bytearray()
            async for chunk in response.aiter_raw(chunk_size=16384):
                if len(chunks) + len(chunk) > MAX_BYTES:
                    raise ResultDenied("size_limit")
                chunks.extend(chunk)
    try:
        envelope = json.loads(
            chunks, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
    except (ValueError, RecursionError):
        raise ResultDenied("invalid_json") from None
    if (
        not isinstance(envelope, dict)
        or envelope.get("jsonrpc") != "2.0"
        or envelope.get("id") != request_id
    ):
        raise ResultDenied("invalid_envelope")
    if "error" in envelope or not isinstance(envelope.get("result"), dict):
        raise ResultDenied("upstream_error")
    return envelope["result"]


def inspect_result(result, mode, evaluate):
    """Inspect the entire JSON tree, including metadata and object keys, before extraction."""
    if mode not in {"audit", "block", "redact"}:
        raise ResultDenied("invalid_mode")
    content = result.get("content", [])
    if not isinstance(content, list) or any(
        not isinstance(part, dict)
        or part.get("type") != "text"
        or not isinstance(part.get("text"), str)
        for part in content
    ):
        raise ResultDenied("unsupported_content")
    if "structuredContent" in result and not isinstance(
        result["structuredContent"], dict
    ):
        raise ResultDenied("unsupported_content")
    if "content" not in result and "structuredContent" not in result:
        raise ResultDenied("unsupported_content")
    findings = set()
    strings = []
    count = 0
    size = 0

    def text(value):
        nonlocal size
        size += len(value.encode("utf-8"))
        if size > MAX_BYTES:
            raise ResultDenied("size_limit")
        strings.append(value)
        clean, labels = redact_secrets(value)
        findings.update(labels)
        return clean

    def walk(node, depth=0):
        nonlocal count
        count += 1
        if depth > MAX_DEPTH or count > MAX_NODES:
            raise ResultDenied("structure_limit")
        if isinstance(node, str):
            clean = text(node)
            if node.lstrip().startswith(("{", "[", '"')):
                try:
                    nested = json.loads(
                        node,
                        object_pairs_hook=_unique_object,
                        parse_constant=_invalid_constant,
                    )
                except ValueError:
                    pass  # Ordinary text need not be JSON.
                else:
                    # Tool text often embeds JSON; inspect decoded keys/values before later extraction.
                    return json.dumps(walk(nested, depth + 1), ensure_ascii=False)
            return clean
        if isinstance(node, list):
            return [walk(value, depth + 1) for value in node]
        if isinstance(node, dict):
            cleaned = {}
            for key, value in node.items():
                if not isinstance(key, str):
                    raise ResultDenied("invalid_json")
                if text(key) != key and mode != "audit":
                    raise ResultDenied("unsafe_key")
                clean = walk(value, depth + 1)
                # Preserve credential-key context that is lost when walking values alone.
                if isinstance(value, str):
                    _, labels = redact_secrets(key + "=" + value)
                    if labels:
                        findings.update(labels)
                        clean = "[REDACTED:credential]"
                cleaned[key] = clean
            return cleaned
        if node is None or isinstance(node, (bool, int, float)):
            return node
        raise ResultDenied("invalid_json")

    cleaned = walk(result)
    combined = "\n".join(strings)
    _, combined_findings = redact_secrets(combined)
    findings.update(combined_findings)
    if mode == "redact":

        def leaves(node):
            if isinstance(node, str):
                yield node
            elif isinstance(node, dict):
                for key, value in node.items():
                    yield key
                    yield from leaves(value)
            elif isinstance(node, list):
                for value in node:
                    yield from leaves(value)

        if redact_secrets("\n".join(leaves(cleaned)))[1]:
            raise ResultDenied("residual_secret")
    decision = evaluate(combined)
    if (
        not isinstance(decision, dict)
        or decision.get("action") not in {"ALLOW", "WARN", "BLOCK", "APPROVAL"}
        or decision.get("rule_id") == "guard.engine_error"
    ):
        raise ResultDenied("policy_unavailable")
    policy_denied = decision["action"] in {"BLOCK", "APPROVAL"}
    if policy_denied:
        findings.add("response_policy")
    elif decision["action"] == "WARN":
        findings.add("response_policy_warning")
    metadata = {
        "mode": mode,
        "finding_types": sorted(findings),
        "policy_action": decision["action"],
        "inspector_version": 1,
        "result_text_bytes": size,
    }
    if mode != "audit" and policy_denied:
        raise ResultDenied("response_policy")
    if mode == "block" and findings - {"response_policy_warning"}:
        raise ResultDenied("secret_detected")
    redacted = (
        mode == "redact"
        and bool(findings - {"response_policy_warning"})
        and cleaned != result
    )
    metadata["decision"] = (
        "audited" if mode == "audit" else "redacted" if redacted else "allowed"
    )
    return (cleaned if redacted else result), metadata


def _record(registration, metadata, *, check_current):
    from app.core.database import SessionLocal
    from app.core.workspace_context import set_workspace_rls
    from app.models.audit_log import AuditLog
    from app.models.mcp_server import McpServer

    with SessionLocal() as db:
        set_workspace_rls(db, registration.workspace_id)
        if check_current:
            row = (
                db.query(McpServer)
                .filter(
                    McpServer.id == UUID(registration.id),
                    McpServer.workspace_id == UUID(registration.workspace_id),
                )
                .with_for_update()
                .first()
            )
            if (
                row is None
                or row.governance != registration.governance
                or row.url != registration.url
                or (row.transport or "http") != registration.transport
            ):
                raise ResultDenied("registration_changed")
            assert_callable(row.governance)
        action = (
            "mcp.response.inspection_started"
            if metadata.get("decision") == "dispatching"
            else "mcp.response.inspected"
        )
        db.add(
            AuditLog(
                workspace_id=UUID(registration.workspace_id),
                action=action,
                resource_type="mcp_server",
                resource_id=registration.id,
                meta={
                    **metadata,
                    "revision": (registration.governance or {}).get("revision"),
                },
            )
        )
        db.commit()


def call_inspected(registration, tool_name, tool_input):
    from app.guard.policy import evaluate
    from app.runtime.integrations.mcp_client import _run

    mode = response_mode(registration.governance)
    try:
        _record(
            registration,
            {"mode": mode, "decision": "dispatching", "inspector_version": 1},
            check_current=True,
        )
        result = _run(_receive(registration, tool_name, tool_input))
        cleaned, metadata = inspect_result(
            result,
            mode,
            lambda value: evaluate(
                registration.workspace_id,
                "mcp",
                tool_name,
                {"content": value},
                gate="response",
                tool_names_supplied=[tool_name],
            ),
        )
        # Fail closed if authorization changed or audit storage is unavailable.
        _record(registration, metadata, check_current=True)
        parts = [part["text"] for part in cleaned.get("content", [])]
        if not parts and "structuredContent" in cleaned:
            return cleaned["structuredContent"]
        combined = "\n".join(parts) if parts else json.dumps(cleaned)
        try:
            return json.loads(combined)
        except ValueError:
            return combined
    except Exception as exc:
        reason = (
            exc.reason if isinstance(exc, ResultDenied) else "inspection_unavailable"
        )
        try:
            _record(
                registration,
                {
                    "mode": mode,
                    "decision": "withheld",
                    "reason": reason,
                    "inspector_version": 1,
                },
                check_current=False,
            )
        except Exception:
            pass  # Result is still withheld if the audit database is unavailable.
        raise ResultDenied(reason) from None
