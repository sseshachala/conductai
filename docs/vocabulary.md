# Vocabulary Decisions

Canonical terms for user-facing strings. Internal identifiers (models, URLs, DB tables) stay as-is until a versioned rename.

## Canonical (user-facing)

| object | user-facing | internal (do not touch) |
|---|---|---|
| agent | **agent** / **agents** | `workflow_id`, `Workflow` model, `/workflows/*` URLs, `conduct_run_workflow` MCP tool, `workflows` DB table |
| rule/policy | **rule** / **rules** | `/guard/policies/list` URL, `Policy*` field names in API responses, `WorkspaceCustomRule` model |
| pack | **pack** / **packs** (drop the "skill" prefix in UI copy) | `SkillPack` model class, `skill_pack_id` foreign key, seed JSON filenames |

## Where "user-facing" applies

- JSX children in `apps/web/src/**/*.tsx`
- CLI `--help` strings and `click.echo` output in `packages/conduct-cli/`
- MCP tool descriptions
- Blog/marketing/docs prose in `docs/**/*.md` and `apps/web/src/app/(marketing)/**`
- Breadcrumbs, page titles, sidebar labels, toast messages, empty-state copy

## Where it does NOT apply

- Python class names, function names, DB columns, HTTP paths, JSON field names
- Test fixtures and code identifiers
- Comments explaining internal architecture (they can use internal names)

## Rules

1. **New code** uses canonical terms in user-facing strings, always.
2. **Existing code** gets fixed drive-by — when a file is opened for another reason, sweep the strings.
3. **No standalone rename PRs** for vocabulary. Cost > value; low-frequency drift is fine.
4. When you must expose an internal identifier to a user (e.g. a URL fragment), the surrounding copy uses the canonical term. Example: sidebar item "Agents" links to `/workflows`; that's OK.

## Product-vocabulary terms (NOT banned — audit spec was wrong)

Sudhi's product positioning uses **playbook**, **workflow**, **automation**, **marketplace**. These are core product vocabulary. Ignore any audit finding that flags them as banned.

The genuine vocabulary issue is *consistency for the same object*, captured in the canonical table above.

## Enforcement

None automated. Reviews catch drift; drive-by fixes handle history. Add a lint rule when drift measurably hurts.
