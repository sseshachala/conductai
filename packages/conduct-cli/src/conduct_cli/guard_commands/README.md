# Guard CLI Modules

`conduct_cli.guard` owns argument parsing, dispatch, and compatibility exports.
Put new implementations in the relevant module rather than extending that file.

| Module | Responsibility |
| --- | --- |
| `shared.py` | Config paths, config persistence, HTTP requests, terminal colors |
| `policy.py` | Local policy evaluation, policy persistence, lint |
| `hooks.py` | Hook launchers and installation |
| `mcp.py` | MCP client registration and configuration |
| `instructions.py` | Tool instruction files and rules |
| `setup.py` | Install, join, sync, credential refresh, package upgrades |
| `gateway.py` | Gateway URLs, shell configuration, Codex provider setup |
| `discovery.py` | Tool detection, process/config discovery, reporting scans |
| `watch.py` | Background discovery lifecycle |
| `reporting.py` | Status, audit, savings, sessions, event replay |
| `verification.py` | Verification, simulation, approval commands, hook debugging |
| `booster.py` | Booster installation and diagnostics |

Cross-module dependencies use explicit module references. Implementation modules
must not import the `guard` facade to resolve their helpers. The existing watch
subprocess import string remains supported by its compatibility export.

Tests patch helpers at their owning module. Public command dispatch can still be
patched at `conduct_cli.guard`. This extraction does not change discovery,
enforcement, credentials, CLI flags, or on-disk configuration formats.
