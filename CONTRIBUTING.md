# Contributing to Conduct

Thanks for wanting to help. Conduct is a runtime AI governance platform
(Guard + Router) with a canvas UI, playbook engine, and 20+ compliance
packs. Contributions of any size are welcome — bug reports, docs fixes,
new playbooks, tests, and code.

## Ground rules

- **License:** contributions are accepted under the
  [Apache License 2.0](./LICENSE), the same license the project ships
  under. By opening a PR you agree your contribution is licensed under
  Apache 2.0, including its patent grant (see Section 3 of the license).
- **Code of conduct:** by participating you agree to the
  [Contributor Covenant](./CODE_OF_CONDUCT.md).
- **Security issues:** do not open a public issue. Follow
  [SECURITY.md](./SECURITY.md) — email hello@conductai.ai.
- **DCO / sign-off (required):** we don't require a CLA. Instead, every
  commit must be signed off (`git commit -s`), which certifies you have
  the right to submit the change under the project license. See the
  [Developer Certificate of Origin](https://developercertificate.org/).
  PRs without sign-off will be asked to rebase with `-s`.

## Getting started

```bash
git clone https://github.com/sseshachala/conductai
cd conductai
docker compose up            # API on :8000, web on :3000, worker + redis
```

Docs on architecture: `SPEC.md`, `NORTHSTAR.md`, `DESIGN.md`, `ROLES.md`
at the repo root.

## What to work on

Look for issues labelled `good first issue` or `help wanted`. If nothing
fits, open a small proposal issue before writing code — it saves a
round-trip on scope.

The areas that see the most external contribution:

- **New playbooks** — `apps/api/playbooks/*.yaml`. Add a test fixture
  and a short doc block.
- **New guard packs** — see the `conduct-*` packs. Rules are declarative
  JSON; add fixture coverage.
- **UI polish** — `apps/web` is Next.js 14 App Router with Tailwind.
- **Docs and examples.**

Please avoid opening PRs that:

- Rename or restructure large parts of the codebase without prior issue.
- Add a new dependency for something the standard library or an already-
  installed dep can do.
- Introduce a new abstraction for a single call site.

## Development conventions

- **Python:** 3.11+, type hints required, `ruff` + `black` for style.
- **TypeScript:** `strict` mode is on; keep it that way. Avoid `any`.
- **Tests:** every non-trivial change ships a test. Framework:
  `pytest` (API), `vitest` (web unit), `playwright` (web e2e).
- **Commits:** conventional-ish. `feat:`, `fix:`, `chore:`, `docs:`,
  `test:`. Body explains the **why**, not the **what**.
- **PRs:** small and focused. One reviewable change per PR. If it needs
  to touch four packages, propose the split in an issue first.

## PR checklist

Before you open the PR:

- [ ] Tests pass locally (`docker compose exec api pytest`, `pnpm test`).
- [ ] TypeScript compiles (`cd apps/web && pnpm typecheck`).
- [ ] Commit messages describe the why.
- [ ] Docs updated if behaviour changed.
- [ ] No secrets, no personal data, no customer names.

Your PR will be reviewed by a maintainer. Expect follow-up questions —
we ask them because we're trying to keep the codebase small and
understandable, not because your work isn't welcome.

## Getting help

- Open a
  [Discussion](https://github.com/sseshachala/conductai/discussions).
- Email hello@conductai.ai for anything that isn't a public issue.

Thank you.
