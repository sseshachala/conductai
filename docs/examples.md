# Examples

37 pre-built playbooks. Every one is a working YAML file under [`apps/api/playbooks/`](../apps/api/playbooks/) — copy, tweak, install. Grouped by what they *do*, not by which tool they call.

Install one directly:

```bash
conduct install pr-reviewer --project MyProject --repo owner/repo
```

Install all 37:

```bash
conduct install-all --project MyProject --repo owner/repo
```

---

## Code review

Every PR gets a first-pass AI review before a human looks at it.

- **[PR Reviewer](../apps/api/playbooks/pr-reviewer.yaml)** — Every PR reviewed for bugs, security issues, and style. Review comment posted automatically.
- **[Bulk PR Reviewer](../apps/api/playbooks/bulk-pr-reviewer.yaml)** — Review all open PRs in a repo in one run. Posts a fleet summary to Slack.
- **[Copilot / AI PR Reviewer](../apps/api/playbooks/copilot-reviewer.yaml)** — AI-authored PRs get a second AI review — catches what Copilot and Cursor miss before humans touch it.
- **[Terraform Plan Reviewer](../apps/api/playbooks/terraform-reviewer.yaml)** — Terraform PRs reviewed for security misconfigs, cost anomalies, and drift.

---

## Security scanning

Catch known-bad patterns before they land.

- **[Security Scanner](../apps/api/playbooks/security-scanner.yaml)** — Every PR scanned for OWASP Top 10, hardcoded secrets, vulnerable dependencies.
- **[Multi-Repo Scanner](../apps/api/playbooks/multi-repo-scanner.yaml)** — Fleet-wide security scan across many repos in parallel; ranked findings.
- **[BugHunter Active Scan](../apps/api/playbooks/bughunter-active-scan.yaml)** — Dynamically loads skills from a configurable GitHub repo (default: `elementalsouls/Claude-BugHunter`).
- **[Threat Modeler](../apps/api/playbooks/threat-modeler.yaml)** — Auto-drafts a STRIDE threat model on every PR that changes architecture, services, endpoints, or trust boundaries.
- **[Codebase Guard Monitor](../apps/api/playbooks/codebase-guard-monitor.yaml)** — Every PR scanned for security violations before merge.

---

## Security auto-fix

Turn a finding into a merged PR.

- **[Security Autopilot Fix](../apps/api/playbooks/security-autopilot-fix.yaml)** — Reads the affected file, writes a targeted patch, opens a PR.
- **[Security Patch Updater](../apps/api/playbooks/security-patch-updater.yaml)** — Dependabot alerts patched, tested, and PR'd with a clear CVE reference.
- **[Security Loop](../apps/api/playbooks/security_loop.yaml)** — Auto-triage security findings from any AI tool or scanner that posts to the findings endpoint.
- **[Third-Party Autopilot Fix](../apps/api/playbooks/thirdparty-autopilot-fix.yaml)** — Fork any third-party repo, apply the fix, open a PR back to upstream.

---

## Dependencies

- **[Dependency Audit](../apps/api/playbooks/dependency-audit.yaml)** — Iterate outdated deps, assess risk per package, open GitHub issues for major upgrades. Supports npm, pip, cargo, go modules.
- **[Dependency Updater](../apps/api/playbooks/dependency-updater.yaml)** — Outdated deps bumped and PR'd automatically every week.

---

## Incidents & alerts

Alert fires → root cause hypothesis is in Slack in under 60 seconds.

- **[Incident Responder](../apps/api/playbooks/incident-responder.yaml)** — Reads the alert, correlates recent commits + deploys, posts a structured hypothesis to `#incidents`.
- **[CI Failure Alert](../apps/api/playbooks/ci-notify.yaml)** — Failed builds diagnosed and explained in Slack before anyone opens a terminal.
- **[Postmortem Drafter](../apps/api/playbooks/postmortem-drafter.yaml)** — Structured postmortem drafted automatically when an incident closes.
- **[Flaky Test Detective](../apps/api/playbooks/flaky-test-detective.yaml)** — Flaky tests identified, traced to the offending commit, fix recommendation lands in Slack + GitHub.

---

## Releases

- **[Release Gating](../apps/api/playbooks/release-gating.yaml)** — Readiness checks + HITL approval + auto-tag + release notes on approval.
- **[Release Readiness Reviewer](../apps/api/playbooks/release-readiness.yaml)** — Go/no-go in Slack — open blockers, failed CI, pending reviews, unresolved incidents.
- **[Release Notes Drafter](../apps/api/playbooks/release-notes.yaml)** — Tag a release → notes drafted automatically.

---

## AI governance

Governance for the AI tools your team uses.

- **[AI Drift Detector](../apps/api/playbooks/ai-drift-detector.yaml)** — Daily check for AI governance drift.
- **[AI Output Auditor](../apps/api/playbooks/ai-output-auditor.yaml)** — Weekly audit of AI tool outputs. Samples the Guard audit log, checks accuracy/bias/quality, posts a scorecard to Slack.
- **[AI Risk Assessment](../apps/api/playbooks/ai-risk-assessment.yaml)** — Pre-deploy checklist for any new AI tool. Surfaces risks, sets data boundaries, defines human controls, generates a one-page incident response plan.
- **[AI Incident Drill](../apps/api/playbooks/ai-incident-drill.yaml)** — Quarterly simulation of an AI governance incident.
- **[Compromised Support Agent](../apps/api/playbooks/compromised-support-agent.yaml)** — Autonomous support agent picks up a ticket containing a prompt injection — Guard blocks, audit trail captures.

---

## Autopilot & issue automation

Label an issue, walk away, come back to a merged PR.

- **[Autopilot — GitHub Issues](../apps/api/playbooks/autopilot.yaml)** — Label an issue `autopilot ready`. Claude implements the fix, runs tests with inline retry, opens the PR.
- **[Autopilot Approved](../apps/api/playbooks/autopilot-approved.yaml)** — Same, but waits for your approval before opening the PR.
- **[OSS Issue Sweep](../apps/api/playbooks/oss-issue-sweep.yaml)** — Every open issue mapped for cross-issue deps, ordered by blast radius, then fixed and PR'd in order.
- **[Issue Triage](../apps/api/playbooks/issue-triage.yaml)** — New issues labeled, prioritized, clarified automatically.

---

## Testing

- **[Smoke Test — Pipeline Ping](../apps/api/playbooks/smoke-test.yaml)** — Prove the full pipeline is healthy in under 30 seconds.
- **[Multi-Env Smoke Test](../apps/api/playbooks/multi-env-smoke-test.yaml)** — Smoke tests across multiple environments in one run.
- **[Acme Onboarding E2E](../apps/api/playbooks/acme-onboarding-e2e.yaml)** — Full role-coverage E2E test using Peekaboo (macOS GUI automation via MCP).

---

## Docs

- **[Docs Drift Detector](../apps/api/playbooks/docs-drift-detector.yaml)** — Merged PRs that break the docs get a follow-up PR automatically.

---

## NetOps

- **[Network Diagnosis Agent](../apps/api/playbooks/network-diagnosis-agent.yaml)** — Autonomous NetOps agent diagnoses a branch incident, correlates telemetry + config changes, proposes remediation, executes only the reversible parts.
- **[Self-Driving Network — Prod Config Push (HITL)](../apps/api/playbooks/self-driving-network-approval-demo.yaml)** — Multi-fabric NetOps (Juniper Mist + Aruba Central) — synchronized config push with human approval gate.

---

## Writing your own

Every playbook above is a self-contained YAML file — 100 to 500 lines each — and they compose from the same block types (`brain`, `http_call`, `slack_post`, `github_*`, `run_shell`, `for_each`, `plan_fix`, `clarify`, `record_outcome`, ...). Pick the closest existing playbook, copy it, edit inputs and blocks.

See [Concepts → Playbooks](mental-models/08-playbooks.md) for the block-type reference and [ADR-0004](adr/ADR-0004-playbook-dsl-versus-external-orchestration-frameworks.md) for the design rationale.
