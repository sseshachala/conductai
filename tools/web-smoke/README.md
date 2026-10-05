# Web Smoke

Both `.github/workflows/nightly.yml` (the `web-smoke` lane) and
`.github/workflows/web-smoke.yml` run the same Playwright suite against a
fresh Postgres/Redis/API stack and a production web build.

Required GitHub Actions secrets:

- `CLERK_TEST_PUBLISHABLE_KEY`
- `CLERK_TEST_SECRET_KEY`
- `CLERK_TEST_PASSWORD_ADMIN`
- `CLERK_TEST_PASSWORD_SECURITY`
- `CLERK_TEST_PASSWORD_DEVELOPER`
- `CLERK_TEST_PASSWORD_VIEWER`

The four sandbox accounts are `admin@example.com`, `security@example.com`,
`developer@example.com`, and `viewer@example.com`. Their Clerk IDs are passed
to `seed_e2e_workspace.py` by the workflows.

`prepare.mjs` validates the sandbox configuration and derives
`CLERK_FRONTEND_API` from the publishable key using Clerk's parser. The optional
`CLERK_TEST_FRONTEND_API` secret, when set, must match. Missing credentials
fail setup; CI does not fall back to dev-mode admin or omit the role matrix.

Run the full nightly browser lane on a branch:

```bash
rtk proxy gh workflow run nightly.yml --ref <branch> -f only=web-smoke
```

Chromium covers all static pages, golden flows, and the four-role matrix.
Firefox covers the golden flows. Conduct API requests and Clerk authentication
are live. The optional Narratr marketing widget scripts are stubbed in the
page sweep because their origin allowlist rejects localhost.

On failure, download the Playwright report and traces from the run's artifacts.
Auth-setup screenshots are uploaded separately. Saved session-cookie JSON is
never uploaded.

## Nightly Failure Triage: September 14 - October 4, 2026

All 21 open web-smoke reports were inspected using their failed steps and
Playwright annotations. The September 29 traces were also inspected.

| Issue | Date | Failed step | Failed tests |
| --- | --- | --- | --- |
| #1940 | September 14 | Playwright | 22 |
| #1972 | September 15 | Playwright | 51 |
| #2011 | September 16 | Playwright | 45 |
| #2055 | September 17 | Playwright | 29 |
| #2090 | September 18 | Playwright | 30 |
| #2136 | September 19 | Playwright | 28 |
| #2147 | September 20 | Playwright | 27 |
| #2180 | September 21 | Playwright | 25 |
| #2198 | September 22 | Playwright | 37 |
| #2216 | September 23 | Playwright | 27 |
| #2222 | September 24 | Playwright | 26 |
| #2232 | September 25 | Playwright | 24 |
| #2247 | September 26 | Playwright | 27 |
| #2256 | September 27 | Playwright | 38 |
| #2272 | September 28 | Playwright | 32 |
| #2290 | September 29 | Playwright | 33 |
| #2301 | September 30 | Playwright | 40 |
| #2307 | October 1 | API startup | Not run |
| #2321 | October 2 | API startup | Not run |
| #2330 | October 3 | API startup | Not run |
| #2337 | October 4 | API startup | Not run |

Recurring causes:

- Empty `CLERK_TEST_FRONTEND_API`: API startup now rejects it. Older builds
  could fall back to dev authentication, undermining the browser role tests.
- The page sweep classified canceled Next.js redirects, RSC prefetches, and
  server actions as failed API calls. API calls are now classified by origin
  and API path; real API errors still fail.
- Auth callback and playbook submission pages had no `main` landmark.
- Responsive fixtures matched `/api/**`, but CI calls the API directly on
  port 8000. Their requests were not intercepted.
- Packs queried an absent score for every playbook, producing dozens of
  expected 404s. They now load the existing submissions collection once.
- Narratr's optional marketing widget returned 403 on localhost.
- On-demand compilation in `next dev` contributed to navigation timeouts.
  CI now builds once and tests `next start`.

Historical console warnings and other intermittent failures remain subject to
the full current-branch run; a triage count alone is not a passing result.
