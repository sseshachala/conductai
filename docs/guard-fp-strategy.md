# Guard False-Positive Strategy

**False positives (FPs) in Guard = rules that fire on legitimate input.**
Example: `owasp_crypto_guard` matches `md5` in a comment describing a
completed migration away from MD5. Both production fires and missing-fixture
gaps are the same problem, sampled at different points.

## The loop

```
prod FP fires ──► audit log entry ──► classify by archetype ──►
    ├─ immediate: kill-switch OR narrow regex
    └─ durable:  negative fixture in tests/fixtures/guard_packs/<pack>.yaml
                     └─► ratchet drops in test_guard_pack_coverage.py
                              └─► same archetype covered for every future rule
```

## Five FP archetypes

| Tag | Pattern shape | Realistic benign form |
|---|---|---|
| **A** | Pattern appears in a code comment | `# Legacy MD5 removed 2024-03-01` |
| **B** | Pattern appears in an import or reference | `from hashlib import sha1  # compat with old signatures` |
| **C** | Pattern appears in a test / fixture | `assert detects_sql_injection("SELECT * FROM users")` |
| **D** | Env-var reference replaces the literal | `password = os.environ["DB_PASSWORD"]` |
| **E** | Pattern appears in doc / markdown copy | RST or markdown listing patterns for security education |

## Priority (highest customer risk first)

1. **Proxy content matchers** (3 rules) — customer-visible LLM blocks
2. **Hook rules by exposure** — top 10 patterns that appear in real code
   (`md5`, `sha1`, `eval`, `execute`, `password=`, `subprocess.call`,
   `console.log`, `print(email`, `DEBUG`, `pickle.load`)
3. **Rest of hook clusters** — batched by archetype, not by pack

## PR pattern (mandatory)

Every FP fix PR includes:

1. **Archetype tag** — one of A–E in the title
2. **Prod signal or plausible-input review** — no made-up benign strings
3. **Negative fixture** in the pack YAML
4. **Regex tune** if applicable (comment-line exclusion, word boundary, etc.)
5. **Ratchet decrement** in `apps/api/tests/test_guard_pack_coverage.py`

## Anti-patterns

- Adding an "obviously benign" fixture with no archetype tag — passes the
  ratchet but doesn't reflect a real FP class
- Fixing one regex without asking "which archetype am I in, and are there
  10 other rules with the same shape"
- Kill-switching a rule and forgetting to file the durable fix

## Ratchet dials (2026-08-27 baseline)

- `COVERAGE_ALLOWANCE = 66` — rules with 0 fixture cases at all
- `NEGATIVE_CASE_ALLOWANCE = 95` — covered rules with 0 negative case
- **Target:** both dials reach 0 by end of Q4

## Scope split for reference

Of the 161 rules missing a negative case:

- **3** are proxy_content scope (fire on LLM prompt text) — customer-visible
- **158** are hook scope (fire on tool_input: edit / write / bash / shell / etc.)

Most of the FP surface lives in hook rules over code content — the archetype
model above biases toward that reality.

## Escape hatch

If a single rule ships hot with a real customer FP incident, kill-switch
it immediately without waiting for the archetype pass. Log the FP class
in this doc's changelog afterwards.

## Related

- Ratchet audit: `apps/api/tests/test_guard_pack_coverage.py`
- Matrix runner: `apps/api/tests/test_guard_pack_matrix.py`
- Fixture location: `apps/api/tests/fixtures/guard_packs/*.yaml`
- Pack sources: `apps/api/app/modules/guard/skill_packs/conduct-*.json`
- Tracking issue: #1272 (fixture backfill)
- Parent epic: #1258 (test coverage plan)
