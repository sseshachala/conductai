# Changelog

All notable changes to conduct-cli are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

---

## [0.9.0] - 2026-08-09

### Added
- Pretouse hook: obfuscation pre-decode. Every input is also scanned in base64-, hex-, URL-decoded, ROT13, and NFKC-normalized variants before rule matching. Encoded override payloads can no longer bypass pattern rules.
- Rules can opt in to decoded-only matching by setting `"scan": "decoded"`. Otherwise every pattern rule now scans both raw and decoded variants automatically.

### Notes
- Ship the new `conduct-prompt-injection` skill pack (30 rules covering override, role hijack, delimiter escape, system-prompt disclosure, encoded canaries, unicode tag smuggling, credential exfiltration, and more) via `conduct sync` after upgrading.

---

## [0.8.9] - 2026-08-09

### Security (#1049)
- Pretouse hook: removed `/docs/` and `/apps/web/src/` from DEV_PATH_MARKERS — those substrings appear in most Next.js/documentation projects and previously caused doc-sensitive framework rules (IRS 1075, ISO 42001 responsible-use, NIST/EU AI docs) to silently skip in customer repos.
- Remaining Conduct-specific dev markers now require a `.conduct-dev-repo` sentinel file at the repo root to activate. Without the sentinel, all framework rules apply on every path.

---

## [0.8.8] - 2026-08-08

### Fixed (#1048)
- Pretouse hook: doc-sensitive rules (IRS 1075, ISO 42001 responsible-use, NIST measure/govern-doc, EU AI PII) no longer false-fire on developer source paths (`apps/api/`, `packages/conduct-cli/`, `docs/`, etc.)
- Pretouse hook reads a rule's `except_paths` field for declarative per-rule exclusions
- ISO 42001 `responsible-use` pattern narrowed to require LLM invocation proximity (`anthropic.messages.create`, `openai.chat.completions.create`, etc.) instead of matching any occurrence of the word "model"
- Block/warn messages now prepend `[rule_id]` so users know which rule fired
- Guard sync propagates `except_paths` and `source_pack` fields to the client policy

### Added
- `conduct import-cedar <file>` — import a Cedar policy bundle as a Guard pack; `--install` flag installs the pack in one step

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
