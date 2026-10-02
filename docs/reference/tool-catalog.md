# Tool catalog

`config/tool_catalog.json` is the versioned source for tool identities,
display names, executable detection names, Gateway protocol selection, and
scoped adapter configuration.
`config/tool_catalog.schema.json` defines its format.

The CLI ships an identical copy in `conduct_cli/tool_catalog.json` so installed
wheels work without the repository. Update both files together; the conformance
test rejects drift. The API bundles the same catalog in
`apps/api/app/core/tool_catalog.json`; update all three copies together.
Web Tool Setup imports the source directly.

This catalog is metadata, not an authorization policy or installation status.
It cannot execute commands or declare an installation verified/protected.
`gateway: null` means no shared Gateway adapter is declared yet, not that the
tool can never support one. `setup_ui` preserves the currently implemented setup
panels. Cursor and Windsurf now expose configuration evidence with live tests pending.
`live_acceptance` is release-level test status, not live device evidence.

Codex CLI and Desktop are listed as distinct surfaces under the existing
`codex` inventory identity. This increment does not migrate installation IDs
or change session deduplication.

## Adding a tool

1. Add its metadata to the source and bundled catalog.
2. Declare `adapter` configuration locations and run adapter conformance tests.
3. Declare a Gateway route only when the matching adapter exists.
4. Run catalog conformance, discovery, and Tool Setup tests.
5. Keep live acceptance pending until a real installation has been tested.

## Adapter behavior

`conduct_cli.tool_adapters` builds its registry from each catalog entry's
versioned `adapter` contract. Common JSON/TOML MCP discovery needs no new
Python registry entry. Manifests cannot import code or execute commands.

| Field | Values |
|---|---|
| `version` | `1` |
| `platforms` | `darwin`, `linux`, `win32` |
| `home` | Path segments relative to the user's home |
| `home_env` | Optional custom config-home variable |
| `mcp` | Ordered configuration sources, later scopes override earlier ones |
| `hooks` | Built-in hook handler, or `null` |
| `usage` | Built-in usage reader, or `null` |

An MCP source declares `anchor`, `path`, `scope`, and `key`. Anchors are
`root`, `project`, or `root-sibling` (Claude's sibling `.json` file only).
Paths cannot be absolute, contain parent traversal, expand environment
variables, or escape the selected project through symlinks. Project files
are read only when the user selects that project.

For a new JSON-based agent, start with:

```json
{
  "version": 1,
  "platforms": ["linux"],
  "home": [".example-agent"],
  "home_env": null,
  "mcp": [{"anchor": "root", "path": "mcp.json", "scope": "user", "key": "mcpServers"}],
  "hooks": null,
  "usage": null
}
```

Handler names select existing trusted implementations; they do not install
plugins or imply compatibility with another tool's protocol. A new hook or
usage protocol still needs an implementation and tests. Platform declarations
are support metadata, not proof of live verification. Keep `setup_ui: false`
for a discovery-only tool. Catalog changes ship with the CLI/API release;
remote manifest downloads and executable third-party plugins are not enabled.

`conduct guard discover --config-only --no-verify-gateway` reads user config
and reports all configured MCP references, not only Conduct. Add
`--project /path/to/project` to include that project's supported config files.
No recursive repository scan, server launch, environment expansion, or remote
MCP connection occurs. Uploaded records contain a hashed reference ID, safe
server identifier, scope, transport, and disabled status. URLs, commands,
arguments, environment variables and credentials are not uploaded.

Reference IDs distinguish project/user sources. They do not assert that two
references are the same running server, or that a server's tools are trusted.
The UI shows these records under the installation's Evidence view. Stale scan
timestamps still apply to those records.

## Cursor and Windsurf

`conduct guard sync` installs the editor hook adapters when their config roots
exist. `conduct guard editor-hooks --tool cursor` or `--tool windsurf` can
install them separately. Add `--remove` to remove only Conduct's editor hooks;
it does not remove other hooks, MCP servers, credentials or the editor.

| Surface | Before execution | After execution | Live acceptance |
|---|---|---|---|
| Cursor Agent | Generic preToolUse policy check | Post/failure metadata | Pending |
| Windsurf Cascade | Read/write/command/MCP policy check | Execution metadata | Pending |

Cursor's blocking hooks set `failClosed: true`. The adapter child check has a
20-second timeout and denies on errors or missing policy. Windsurf blocks via
exit code 2 when the adapter runs; failures to launch the adapter are governed
by the host's hook implementation. Post hooks cannot stop completed operations
or redact responses. These adapters do not install a Gateway route or invent
session-token counters. Existing workspace policy fail-mode settings still apply
inside the shared policy engine.

Windsurf scope here is the existing Cascade layout under
`~/.codeium/windsurf`, not the newer Devin Local agent. Supported native hook
behavior must be confirmed on each deployed editor version.

References: [Cursor hooks](https://cursor.com/docs/hooks),
[Windsurf/Cascade hooks](https://docs.windsurf.com/windsurf/cascade/hooks),
[Claude MCP scopes](https://code.claude.com/docs/en/mcp).

## Remaining epic scope

Registered MCP server review and client usage categories are described in
[MCP review and session usage](tool-review-and-usage.md).

Executable third-party adapter installation, per-tool version constraints,
remaining lifecycle operations, and request-level spend reconciliation remain
in #2309. Registered MCP response inspection and device registration links
are documented in the reference above.
