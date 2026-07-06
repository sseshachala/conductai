# Changelog

All notable changes to conduct-cli are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

---

## [0.7.3] - 2026-07-06

### Fixed
- `conduct guard discover` now correctly detects Codex as covered by reading `~/.codex/config.toml` and `hooks.json` instead of the non-existent `mcp.json`
- Discover scan 500 error resolved — agents are deduped by (framework, source) before upsert to avoid unique constraint violation

---

## [0.7.2] - 2026-07-06

### Fixed
- `conduct verify` now reads the `ts` field from API events; was previously looking for `timestamp`/`created_at` which do not exist

---

## [0.7.1] - 2026-07-06

### Fixed
- `no-rm-rf` rule now maps to OWASP A04 (Excessive Agency)
- `no-sudo` rule now maps to OWASP A09 (Privilege Escalation)

---

## [0.7.0] - 2026-07-06

### Added
- Hash-chain audit log — every guard event records `previous_hash` and `entry_hash` (SHA-256 chain); verify integrity with `GET /guard/events/audit/verify`
- Advisory mode — `advisory_mode` flag on guard config; when enabled, all actions are logged as "audited" instead of blocked; hook exits 0; MCP returns ALLOWED; `conduct guard sync` shows an `advisory` badge
- Decision BOM — `policy_hash` column on every audit event snapshots the active policy version at decision time
- `conduct verify [--evidence FILE] [--strict] [--format text|json]` — maps guard events to OWASP Agentic Top 10; `--strict` exits 1 in CI if any blocked events are present
- Fail-closed on policy eval error — `deny_on_error` flag (default true); policy engine errors record a blocked audit row with `rule_id=policy_eval_error` instead of silently allowing

### Changed
- Updated marketing and docs framing to "structurally impossible" for tampered audit claims

---

## [0.6.37] and earlier

See git history for earlier releases.
