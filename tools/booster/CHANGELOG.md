# Changelog

## 0.8.0 — 2026-10-10

Language coverage release.

- **New languages:** Go, Rust, Java, C, C++, shell, YAML — driven by one table in `booster/langs.py` (extension → grammar, symbol node types, call node types) and a generic tree-sitter walker. Python/TS keep their existing collectors.
- **YAML:** top-level keys, `section.key` mappings (playbook `blocks.*`, GitHub Actions `jobs.*`, compose `services.*`), and shallow list items with `id:`/`name:`.
- **Read gate:** `booster smart-read` with no task (the hook path) passes YAML through to a full Read — also fixes already-installed hooks.
- File discovery prunes skip dirs (adds `target`, `vendor`) and skips files over 1 MB; test-file detection covers `_test.go`, `*Test.java`, `_test.c[c|pp]`.
- `eval/`: +10 YAML/shell queries (44 total). On this repo RRF R@5 0.75 → 0.98.

**Upgrade:** `pip install -U agent-booster`, then `booster index --embed` to pick up the new files.

## 0.7.0 — 2026-10-09

Search quality release.

- **Keyword search → SQLite FTS5 + bm25.** Any-term match, porter stemming, name column weighted 5×, camelCase/snake_case split into words. Falls back to `LIKE` when sqlite lacks FTS5.
- **Embeddings cover name + signature + doc snippet** (leading comment + first 10 body lines), not name + signature only.
- **Model → `BAAI/bge-small-en-v1.5`** with its query instruction. Vectors are stamped with the model name (`.booster/vectors_model.txt`); mismatched vectors and old daemons are ignored, never mixed.
- **`route_model`:** a complexity keyword no longer forces opus when scope is a single file; scattered search hits can't escalate past sonnet.
- `indexer.py` split into `parsing`, `git_util`, `schema`, `embed`, `search`, `graph` (old import paths still work).
- `eval/`: 34-query recall eval. On this repo RRF R@5 0.62 → 0.97, MRR 0.47 → 0.88; keyword R@5 0.00 → 0.91.

**Upgrade:** the schema migrates on first open and marks every file for re-parse. Run `booster index --embed` once (downloads bge-small, ~130 MB) and restart the daemon (`booster stop && booster start`).

## 0.3.0 — 2026-06-26

Context completeness release. Three new MCP primitives, two free-fold upgrades to existing tools, zero new runtime dependencies.

### New MCP tools

- **`expand_calls(symbol, direction, depth, file?)`** — return immediate callers or callees of a symbol, with cycle-safe depth expansion (1-3). Same-file resolution at index time; cross-file resolution is name-based at query time. Documented accuracy: ~70% on Python, lower on TS code that uses overloads or runtime dispatch.
- **`test_coverage(symbol, file?)`** — return test references for a symbol. Populated via `booster index --tests`. Coarse substring + import heuristic in v0.3.0; coverage.py runtime integration deferred.
- **`smart_read(file, task, since?)`** — `since` is new. Pass any git ref (`HEAD~5`, `main`, SHA) to restrict the slice to symbols whose lines changed in that range.
- **`search_context(task, since?)`** — `since` is new. Same semantics as above; restricts results to recently-changed symbols.

### Free folds (no new API)

- `smart_read` output now includes a `[last_modified: <sha> <date>]` header per symbol when git blame is available.
- `search_context` ranking is nudged toward files with high historical read counts (from local stats.db). Silent fallback when stats are empty.

### CLI changes

- `booster index --tests` — populate the test-coverage index. Run after `booster index` or alongside it.

### Schema

- New columns on `symbols`: `commit_last_modified TEXT`, `last_modified_ts INTEGER`. Populated via batched `git blame --line-porcelain` per file (one subprocess per file, max-timestamp commit per symbol range).
- New table `symbol_edges` (call graph) with indexes on `source_id`, `target_name`, `file`.
- New table `symbol_tests` (test references) with indexes on `symbol_id`, `symbol_file`, `test_file`.
- Migration is automatic and idempotent on first open of an existing v0.2.x `.booster/symbols.db`.

### Backward compatibility

- All existing MCP tools and CLI commands are unchanged in surface and semantics. Optional new parameters default to current behavior.
- `booster gain -f json` output is **field-stable**: every key the conduct-cli consumer relies on (`active_days`, `total_reads`, `full_tokens`, `slice_tokens`, `saved_tokens`, `savings_pct`, `top_files`, `crusher.*`) is preserved. Snapshot test in `tests/test_v030.py` guards the contract.
- Existing `.booster/symbols.db` from v0.2.x migrates in place — no reindex required. Run `booster index --force` to populate the new `last_modified` columns for already-indexed symbols.

### Known limits (documented, not bugs)

- Call resolution is name-based. A function `foo` defined in multiple unrelated files will produce false positives. Disambiguate with the optional `file` argument to `expand_calls`.
- `test_coverage` uses substring matching with a 3-character floor on symbol names. Tests that reference symbols only through fixtures, parametrize, or dynamic dispatch are not detected. Upgrade path: coverage.py runtime integration (future).
- Diff-aware reads (`--since`) include the working tree by default; staged-but-uncommitted changes count as "since HEAD".

### Upgrade

```bash
pip install -U agent-booster
booster index --force      # populate new last_modified columns
booster index --tests      # opt-in, builds test_coverage index
```

No conduct-cli changes required. New MCP tools (`expand_calls`, `test_coverage`) are auto-discovered by any agent host pointed at `booster serve`.

## 0.2.x

See git history.
