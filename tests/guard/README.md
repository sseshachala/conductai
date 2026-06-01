# Conduct Guard — UI Test Harness

Automated browser test harness for the Guard feature, covering all four roles:
**admin**, **security**, **editor**, and **viewer**.

Uses [Stagehand](https://github.com/browserbasehq/stagehand) (AI-driven browser
automation with headless Chromium) to navigate the UI and capture screenshots.
No human touch is required during a run.

---

## Prerequisites

### 1. Environment variables

Create a `.env` file in this directory (or export in your shell):

```sh
# Clerk backend secret — Clerk dashboard → API Keys → Secret key
CLERK_SECRET_KEY=sk_test_...

# Clerk publishable key — used to derive the Clerk frontend API URL
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...

# Anthropic API key — used by Stagehand's Claude vision model
ANTHROPIC_API_KEY=sk-ant-...

# URL where the Conduct Next.js app is running
CONDUCT_APP_URL=http://localhost:3000

# URL where the Conduct FastAPI backend is running
CONDUCT_API_URL=http://localhost:8000
```

Optional (CI/pre-baked token):

```sh
# If you have a long-lived Conduct API JWT, set this to skip the
# Clerk token-exchange flow in setup.ts
CONDUCT_ADMIN_TOKEN=<clerk-session-jwt>

# Override the Clerk frontend API URL if your publishable key decoding
# produces the wrong host
CLERK_FRONTEND_API_URL=https://clerk.yourapp.dev
```

### 2. Running services

Both the Next.js app (`apps/web`) and the FastAPI backend (`apps/api`) must be
running before you execute any test commands.

---

## Installation

```sh
cd tests/guard
npm install
```

---

## Usage

### Step 1 — Setup (run once per test session)

Creates four Clerk test users, creates a "Guard Test Workspace", assigns roles,
and writes `test-state.json`.

```sh
npm run setup
```

Safe to run again — upserts users and reuses existing workspaces.

### Step 2 — Run tests

```sh
npm test                  # all 4 roles
npm run test:admin        # admin only
npm run test:security     # security only
npm run test:editor       # editor only
npm run test:viewer       # viewer only
```

Or with explicit role flag:

```sh
tsx runner.ts --role admin,security
```

### Step 3 — View the report

After the run, open:

```
reports/index.html
```

The report contains:
- A role × feature matrix at the top (green tick / red cross per step)
- Per-role sections with numbered steps, pass/fail badges, and inline screenshots
- Duration and timestamp per role
- Overall pass/fail summary

### Step 4 — Teardown (run after testing)

Deletes the Clerk test users. Does **not** delete the test workspace.

```sh
npm run teardown            # delete users, keep test-state.json
npm run teardown -- --clean # also remove test-state.json
```

---

## What each role tests

| Role | Guard access | Key assertions |
|------|-------------|----------------|
| **admin** | Full access | Dashboard loads, all tabs visible, Add rule modal opens, Spend controls Configure accessible, Members list visible |
| **security** | Guard visible, no admin actions | Dashboard loads, Policies and Spend visible, Configure spend absent, Invite member absent |
| **editor** | Redirected from Guard | /guard → /dashboard redirect, Guard absent from sidebar, direct Guard URLs redirect |
| **viewer** | Redirected from Guard | Same as editor |

---

## Test users

| Role | Email | Password |
|------|-------|----------|
| admin | conduct.test.admin@mailinator.com | ConductTest!Admin1 |
| editor | conduct.test.editor@mailinator.com | ConductTest!Edit1 |
| security | conduct.test.security@mailinator.com | ConductTest!Sec1 |
| viewer | conduct.test.viewer@mailinator.com | ConductTest!View1 |

Mailinator addresses require no email delivery — Clerk just validates the format.

---

## Output

```
tests/guard/
├── reports/
│   ├── index.html                  # HTML report (open in browser)
│   └── screenshots/
│       ├── admin/
│       │   ├── 01-login.png
│       │   ├── 02-guard-loads.png
│       │   └── …
│       ├── security/
│       ├── editor/
│       └── viewer/
└── test-state.json                 # workspace + user IDs (gitignored)
```

---

## Debugging

Set `headless: false` in `lib/stagehand.ts` `createBrowser()` to watch the
browser during a run.

Each step is wrapped in a try/catch — a single step failure is recorded and the
flow continues. The runner exits 1 if any step fails.
