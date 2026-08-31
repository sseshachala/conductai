## What this PR does

One or two sentences on the change and the reason for it. Link the
issue if there is one (`fixes #123`).

## Type

- [ ] Bug fix
- [ ] Feature
- [ ] Refactor / internal change (no user-visible behaviour change)
- [ ] Docs
- [ ] Playbook / pack

## Checklist

- [ ] Tests added or updated (or explicit note why not).
- [ ] **Bug fix only:** regression test file:line named below (a test that would fail if the bug returns). Non-negotiable for anything tagged P0 or P1. See `tests/glens/test_lens_canon.py` and `tests/guard/test_guard_canon.py` for the canon manifest — a bug fix without a regression test is unfinished.
- [ ] `pytest` (API) and `pnpm typecheck` (web) pass locally.
- [ ] No secrets, no personal data, no customer names in the diff.
- [ ] Commit messages describe the **why**.
- [ ] Docs updated if behaviour changed.

**Regression test (bug fix only):**
`path/to/test_file.py::test_name` — the test that would have caught this bug.

## How to test

Steps a reviewer can follow to see the change working.

## Screenshots or output

If UI or CLI output changed, paste before/after.
