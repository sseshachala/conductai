# Tool catalog

`config/tool_catalog.json` is the versioned source for tool identities,
display names, executable detection names, and Gateway protocol selection.
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
2. Implement its scoped detection/configuration adapter and tests.
3. Declare a Gateway route only when the matching adapter exists.
4. Run catalog conformance, discovery, and Tool Setup tests.
5. Keep live acceptance pending until a real installation has been tested.

## Adapter behavior

The trusted Python registry in `conduct_cli.tool_adapters` binds each catalog
entry to scoped configuration locations. JSON cannot import code or execute
commands. Unknown catalog entries fail the registry conformance check until an
adapter is implemented and tested.

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

Third-party adapter installation, per-version/platform declarations, MCP response
inspection, device-to-registry reconciliation, and session-to-Gateway spend
reconciliation remain in #2309.
