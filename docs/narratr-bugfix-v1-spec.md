# Narratr Bugfix Autopilot — MVP Spec and Build Plan

## 1. Product Goal
Ship a safe, repeatable workflow that turns GitHub bug issues into reviewable draft PRs with full traceability.

Target outcome:
- Reduce issue-to-draft-PR time for routine bugs.
- Keep human approval before merge.
- Make every action auditable.

## 2. Named User Problem
Engineering teams lose time between bug intake and first valid fix attempt:
- triage latency
- context switching
- repetitive local setup
- slow first PR turnaround

This MVP focuses on one job:
- "Given a labeled bug issue, produce a safe draft PR that compiles/tests and can be reviewed quickly."

## 3. MVP Scope
### In scope
- Trigger from GitHub issue label (`autopilot-ready` or similar).
- Read issue context + repo context.
- Claude Brain proposes and applies code changes in sandbox.
- Build/test locally in isolated runtime.
- Retry fix loop up to configured attempt limit.
- Open draft PR to the logged-in workspace user's GitHub.
- Post run summary + PR link to Slack.
- Persist run trace, token/cost estimate, and outcome metadata.

### Out of scope (v1)
- Auto-merge to protected branches.
- Broad connector marketplace expansion.
- Generic visual workflow builder enhancements unrelated to bugfix autopilot.
- Multi-repo dependency graph reasoning.
- Enterprise SSO/RBAC hardening beyond current baseline.

## 4. What We Already Have (in Marshal)
The current codebase already provides most platform primitives needed for v1.

### 4.1 Workflow platform primitives (already built)
- Canvas workflow editor with block validation, autosave, dry-run, and run launch.
- Workflow CRUD + versioning + compile endpoint.
- Redis queue + worker + runtime executor.
- Run event streaming (SSE) and run history.
- Approval pause/resume API + Slack approval webhook.
- Credential vault (encrypted integration credentials).
- Integrations available: GitHub, Slack, Linear, Vercel, Railway, DigitalOcean.

### 4.2 Existing behavior we can reuse
- Webhook trigger handling for GitHub/Vercel/Railway.
- Brain block with bounded tool loop.
- Tool block invocation by integration/action.
- Cost estimation endpoint for workflows.

## 5. Gaps to Build for Narratr v1
### P0 (must build)
1. **Bug-specific GitHub trigger contract**
- Normalize issue webhook payload for bug workflows.
- Enforce required label + repo allowlist from trigger config (not hardcoded).

2. **Workflow input schema + parameter mapping**
- Explicit inputs: `repo`, `issue_number`, `base_branch`, `label`, `workspace_user`.
- Map webhook payload into params deterministically.

3. **Safe sandbox execution policy**
- Allowed commands list for build/test/fix loops.
- Forbidden paths and max changed files/LOC policy.
- Per-run CPU/time budget with hard timeout.

4. **Compile/build/test orchestration profile**
- Detect project test command (or configurable per repo).
- Structured parsing of failures passed back to Brain.
- Retry loop with attempt cap (e.g. 3).

5. **PR creation policy**
- Always draft PR in v1.
- Standard title/body template with run trace URL and test summary.
- Labels: `ai-generated`, `needs-review`.

6. **Narratr workflow template**
- Prebuilt "GitHub Bug -> Draft PR" template installable in one click.

### P1 (should build soon after)
1. Cost and quality dashboard fields per run:
- attempts, pass/fail reason, files touched, token/cost.
2. Better diagnostics:
- diff summary, failing tests grouped by file/test case.
3. Notification options:
- Slack + optional GitHub issue comment back-link.

### P2 (defer)
1. Auto-assign reviewers by code owner rules.
2. Multi-agent decomposition for large bugs.
3. Cross-repo fixes in one run.

## 6. Workflow JSON Contract (MVP)
```json
{
  "id": "narratr-bugfix-autopilot-v1",
  "trigger": {
    "type": "github_issue_labeled",
    "label": "autopilot-ready",
    "repo_allowlist": ["your-org/narratr-website", "your-org/narratr-social"]
  },
  "inputs": {
    "repo": "string",
    "issue_number": "number",
    "base_branch": "string"
  },
  "policy": {
    "max_attempts": 3,
    "max_changed_files": 25,
    "max_changed_lines": 800,
    "forbidden_paths": [".env", "secrets/", "supabase/migrations/"],
    "allowed_commands": ["npm ci", "npm test", "npm run build", "npm run lint"]
  },
  "steps": [
    "fetch_issue",
    "prepare_repo_sandbox",
    "brain_fix",
    "build_test",
    "retry_if_failed",
    "open_draft_pr",
    "notify"
  ]
}
```

## 7. Execution Flow
1. GitHub webhook arrives for issue-labeled event.
2. Trigger validates label/repo/workspace mapping.
3. Run is queued with normalized input params.
4. Brain reads issue + repo context and proposes edits.
5. Sandbox applies edits and runs build/tests.
6. On failure, structured feedback goes back to Brain (up to max attempts).
7. On success, draft PR is created and linked to issue.
8. Slack notification sent with approve/review CTA.
9. Full run trace persists for audit.

## 8. Success Metrics (first 30 days)
Primary:
- Median issue-to-draft-PR time.
- % runs producing a reviewable draft PR.

Guardrails:
- % runs blocked by policy violations.
- Mean attempts per successful run.
- Runtime and token cost per run.

Quality:
- % draft PRs merged with minor/no edits.
- Reopen/regression rate for autopilot-fixed issues.

## 9. Rollout Plan
### Week 1
- Finalize workflow input schema and webhook mapping.
- Implement repo allowlist + trigger validation.
- Ship v1 workflow template.

### Week 2
- Implement structured build/test loop and retry policy.
- Add policy guards (paths/LOC/commands/timeouts).

### Week 3
- PR templating, labels, issue linking, Slack summary.
- Improve trace events for diagnostics.

### Week 4
- Internal dogfood on Narratr repos.
- Tune prompts/policies from failure logs.
- Lock go/no-go against success metrics.

## 10. Go/No-Go Criteria
Go if all are true:
- >= 60% of autopilot-ready bug issues produce reviewable draft PRs.
- No critical security/policy violations in production runs.
- Median issue-to-draft-PR time is materially lower than current baseline.

No-go / narrow scope if:
- Success rate < 40% after two prompt/policy tuning cycles.
- Frequent unsafe edits or noisy PRs reduce team trust.

## 11. Risks and Mitigations
1. **Unsafe code changes**
- Mitigation: strict policy gates + draft-only PRs + forbidden path checks.

2. **Low fix quality on complex issues**
- Mitigation: tight issue label policy (only scoped bug tickets), fail-fast handoff to human.

3. **High run cost**
- Mitigation: attempt caps, token budgets, smaller context windows.

4. **Flaky test/build environments**
- Mitigation: containerized deterministic sandbox and pinned setup commands.

## 12. Immediate Next Actions
1. Implement workflow input schema and webhook payload mapper.
2. Add policy guard middleware in runtime executor.
3. Create one production-ready Narratr bugfix template and run internal pilot.