# Automate

Wire Conduct into your other tools. CLI, MCP, CI, HTTP.

---

## CLI

`conduct-cli` is the primary programmatic entrypoint. Install with `pip install conduct-cli`; full command reference in the [CLI README](../packages/conduct-cli/README.md).

**Command groups:**

| Group | Purpose |
|---|---|
| `login`, `whoami`, `token` | Auth |
| `projects`, `create`, `delete`, `reset`, `switch` | Workspace/project management |
| `playbooks`, `install`, `install-all`, `agents` | Playbook catalog + installation |
| `test`, `run`, `emit` | Execution + event emission |
| `environments`, `credentials`, `set` | Secrets |
| `guard sync`, `guard status`, `guard audit`, `guard approvals`, `guard discover`, `guard watch` | Guard governance |
| `mcp install` | Register Conduct's MCP server in AI clients |
| `skill list`, `skill install`, `skill uninstall` | Guard policy skill packs |
| `verify`, `test-guard`, `test-security` | Governance evidence + rule testing |

**Exit codes:** `0` success, `1` user/config error, `2` blocked by Guard policy. Machine-parseable output via `--json` flag on most commands.

---

## MCP (Model Context Protocol)

Conduct exposes an MCP server so Claude Code, Cursor, Codex, and any MCP-compatible AI client can call Guard directly. Full spec: [ConductGuard MCP](modules/conductguard/conductguard_mcp.md).

**Install:**

```bash
conduct mcp install
```

Writes MCP server registration into your AI client's config files (`~/.claude/`, `~/.cursor/`, etc.).

**Tools exposed to the AI client:**

- `guard_status` — team, active rules, policy version
- `guard_check` — pre-flight check before executing a tool call
- `guard_sync` — refresh policy from the API
- `guard_activity` — log what the AI is currently doing

**Endpoint (remote):** `https://api.conductai.ai/guard/mcp` — spawned via `npx -y mcp-remote https://api.conductai.ai/guard/mcp` if you prefer no local binary.

---

## CI integration

`conduct-cli` is stateless per-invocation (reads token from `~/.conduct/config.json` or `CONDUCT_TOKEN` env var). Drop it into any pipeline.

**GitHub Actions example:**

```yaml
- name: Install Conduct CLI
  run: pip install conduct-cli

- name: Trigger release-readiness agent
  env:
    CONDUCT_TOKEN: ${{ secrets.CONDUCT_TOKEN }}
    CONDUCT_WORKSPACE: ${{ secrets.CONDUCT_WORKSPACE }}
  run: conduct test "Release Readiness Reviewer" --json
```

**Emit findings from any scanner into Conduct's security loop:**

```bash
conduct emit finding \
  --severity critical \
  --type hardcoded_secret \
  --description "AWS key at src/config.py:42"
```

Findings flow into the [Security Loop](../apps/api/playbooks/security_loop.yaml) playbook for auto-triage.

---

## Hooks (Claude Code, Cursor, Codex)

`conduct guard sync` installs a PreToolUse hook at `~/.conductguard/hook.py` that fires before every AI tool call. Local policy evaluation (no API round-trip), async audit event to the API, exit code 0/2 for allow/block.

Details: [Hook coverage matrix](modules/conductguard/hook_coverage.md).

---

## HTTP API

Every CLI command is a thin wrapper over the HTTP API. Base URL: `https://api.conductai.ai` (or your self-hosted server). Auth: `Authorization: Bearer <token>`.

- **Versioning contract** → [API versioning](api-versioning.md)
- **Interactive schema** → `https://<your-api>/docs` (OpenAPI/Swagger)
- **Machine schema** → `https://<your-api>/openapi.json`

---

## Programmatic execution

For custom orchestration outside the CLI:

- **REST**: hit `POST /workflows/<id>/run` with inputs; poll `GET /runs/<id>` for status.
- **Webhooks (inbound)**: every playbook auto-exposes `https://<your-api>/webhooks/inbound/<workflow-id>` — POST any JSON payload to trigger.
- **Webhooks (outbound)**: subscribe to run lifecycle events under workspace settings.
- **SSE**: `GET /runs/<id>/events` streams live run events.

---

## Next steps

- **Understand the runtime** → [Execution engine](mental-models/01-execution-engine.md), [Brain block](mental-models/02-brain-block.md)
- **Tune governance** → [Policy](README.md#policy)
- **Add a custom Guard rule** → [Enforcement coverage](modules/conductguard/enforcement_coverage.generated.md)
