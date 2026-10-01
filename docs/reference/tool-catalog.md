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
panels; it does not remove Cursor or Windsurf from the implementation scope.
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

This is the first increment of #2309. Executable adapter registration,
per-version/platform capability declarations, MCP integrity, response inspection,
quarantine, and session/spend reconciliation remain subsequent work.
