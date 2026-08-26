# Guard regression harness (Phase 0 for #1218 / #1219)

Byte-parity fixtures + replay tests. Locks in the pre-refactor behavior of the
Guard proxy (`/proxy/*`) and MCP server (`/guard/mcp`) so the #1218 / #1219
rewrite can prove it changes nothing observable.

## When to run

- Before landing any commit that touches `app/modules/guard/routers/proxy.py`,
  `app/modules/guard/routers/mcp.py`, or the new `app/guard/` / `app/mcp/`
  modules being introduced by #1218 / #1219.
- Every PR on branch `feat/1218-guard-gateway-lens`.

If the diff changes any recorded response bytes, DB row, or hash-chain output,
the refactor is not behavior-preserving. Fix the code, not the fixtures.

## Fixture format

Each fixture is a JSON file describing one HTTP request + its expected
observable output.

```json
{
  "name": "proxy_openai_allow_stream",
  "request": {
    "method": "POST",
    "path": "/proxy/openai/v1/chat/completions",
    "headers": {"Authorization": "Bearer cond_live_test_...", "Content-Type": "application/json"},
    "body": {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}], "stream": true}
  },
  "expected_response": {
    "status": 200,
    "content_type": "text/event-stream",
    "stream_chunks": ["data: {...}\n\n", "data: {...}\n\n", "data: [DONE]\n\n"]
  },
  "expected_db_rows": [
    {
      "table": "guard_audit_events",
      "match": {"workspace_id": "<ws_id>", "decision": "allow", "source": "http_proxy"},
      "assert": {"previous_hash": "<prior_entry_hash>"}
    }
  ]
}
```

## Fixtures (8 planned)

| # | File | Scenario |
|---|---|---|
| 1 | `proxy_openai_allow_stream.json` | OpenAI streaming, no block |
| 2 | `proxy_openai_block_pii.json` | Blocked by PII rule (SSN in request) |
| 3 | `proxy_anthropic_allow.json` | Non-streaming Anthropic Messages |
| 4 | `proxy_budget_hit.json` | Workspace spend cap → 429 |
| 5 | `mcp_initialize.json` | MCP JSON-RPC initialize handshake |
| 6 | `mcp_tools_list.json` | `tools/list` returns registered tools |
| 7 | `mcp_tool_call_allow.json` | `guard_status` tool call (allow) |
| 8 | `mcp_tool_call_block.json` | Tool call blocked by policy rule |

## Replay pattern

```python
# tests/regression/test_proxy_parity.py
def test_proxy_fixture(fixture: dict, client: TestClient, db: Session):
    resp = client.request(
        fixture["request"]["method"],
        fixture["request"]["path"],
        headers=fixture["request"]["headers"],
        json=fixture["request"].get("body"),
    )
    assert resp.status_code == fixture["expected_response"]["status"]
    if "stream_chunks" in fixture["expected_response"]:
        assert list(resp.iter_lines()) == fixture["expected_response"]["stream_chunks"]
    else:
        assert resp.json() == fixture["expected_response"]["body"]
    for expected_row in fixture["expected_db_rows"]:
        actual = _query_row(db, expected_row)
        for k, v in expected_row["assert"].items():
            assert actual[k] == v
```

## DB requirements

Uses the same `DATABASE_URL` and Postgres setup as `apps/api/tests/conftest.py`.
No SQLite fallback — Guard hash chain uses Postgres-specific features.

## Baseline capture

Run against main-branch code once to establish the golden output:

```bash
cd apps/api
pytest tests/regression/ --capture-golden
```

The `--capture-golden` flag (implemented in `conftest.py`) writes the actual
response and DB state back into the fixture files. Review the diff, commit, and
that becomes the contract. Subsequent runs assert against the committed values.
