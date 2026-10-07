# Examples

Workflows are Conduct's governed response layer. Guard or an alert detects something, a playbook responds, a human approves each consequential action, and the evidence lands in the audit trail.

20 playbooks ship today. Every one is a working YAML file under [`apps/api/playbooks/`](../apps/api/playbooks/): copy, tweak, install.

Install one directly:

```bash
conduct install incident-responder --project MyProject --repo owner/repo
```

---

## Incident response

Alert fires → investigation, hypothesis, and a proposed next step in Slack.

- **[Incident Responder](../apps/api/playbooks/incident-responder.yaml)**: reads the alert, correlates recent commits and deploys, posts a structured hypothesis to `#incidents`.
- **[Postmortem Drafter](../apps/api/playbooks/postmortem-drafter.yaml)**: drafts a structured postmortem when an incident closes.
- **[AI Incident Drill](../apps/api/playbooks/ai-incident-drill.yaml)**: quarterly simulation of an AI governance incident.
- **[Network Diagnosis Agent](../apps/api/playbooks/network-diagnosis-agent.yaml)**: diagnoses a branch incident, correlates telemetry and config changes, proposes remediation, executes only the reversible parts.
- **[Multi-Env Smoke Test](../apps/api/playbooks/multi-env-smoke-test.yaml)**: verifies health across environments in one run.

---

## Governed production changes

An agent proposes a specific action. A human approves that action with its arguments. It executes, and the evidence is recorded.

- **[Release Gating](../apps/api/playbooks/release-gating.yaml)**: readiness checks, human approval, then tag and release.
- **[Terraform Plan Reviewer](../apps/api/playbooks/terraform-reviewer.yaml)**: Terraform plans reviewed for security misconfigs, cost anomalies, and drift before apply.
- **[Self-Driving Network: Prod Config Push](../apps/api/playbooks/self-driving-network-approval-demo.yaml)**: multi-fabric config push (Juniper Mist + Aruba Central) behind a human approval gate.

---

## AI risk and Guard monitoring

Recurring evidence for security, compliance, and AI governance owners.

- **[Codebase Guard Monitor](../apps/api/playbooks/codebase-guard-monitor.yaml)**: surfaces policy violations and coverage gaps across your repos.
- **[AI Risk Assessment](../apps/api/playbooks/ai-risk-assessment.yaml)**: pre-deploy checklist for a new AI tool. Surfaces risks, sets data boundaries, defines human controls.
- **[AI Output Auditor](../apps/api/playbooks/ai-output-auditor.yaml)**: weekly sample of the Guard audit log, checked for accuracy, bias, and quality. Scorecard to Slack.
- **[AI Drift Detector](../apps/api/playbooks/ai-drift-detector.yaml)**: daily check for AI governance drift.

---

## Autopilot fixes

Fixes that open a PR, with approval before anything ships.

- **[Autopilot](../apps/api/playbooks/autopilot.yaml)**: label an issue `autopilot ready`. The agent implements the fix, runs tests with retry, opens the PR.
- **[Autopilot + Approval](../apps/api/playbooks/autopilot-approved.yaml)**: same, but waits for human approval before opening the PR.
- **[Security Patch Updater](../apps/api/playbooks/security-patch-updater.yaml)**: Dependabot alerts patched, tested, and PR'd with the CVE reference.
- **[Dependency Updater](../apps/api/playbooks/dependency-updater.yaml)**: outdated dependencies bumped and PR'd.
- **[Third-Party Autopilot Fix](../apps/api/playbooks/thirdparty-autopilot-fix.yaml)**: fork a third-party repo, apply the fix, open a PR upstream.

---

## Guard demos

Each shows policy, approval, and audit end to end in a few minutes.

- **[NeMo Guardrails Demo](../apps/api/playbooks/nemo-guardrails-demo.yaml)**: a NeMo-style input rail calls Guard, which blocks a prompt-injection payload and writes a hash-chained audit row.
- **[Compromised Support Agent](../apps/api/playbooks/compromised-support-agent.yaml)**: a support agent hit by prompt injection tries credential harvest and exfil. Guard blocks each attempt.

---

## Writing your own

Every playbook is a self-contained YAML file built from the same block types (`brain`, `http_call`, `slack_post`, `github_*`, `run_shell`, `for_each`, `plan_fix`, `approval`, `record_outcome`, ...). Pick the closest playbook, copy it, edit inputs and blocks.

See [Concepts → Playbooks](mental-models/08-playbooks.md) for the block-type reference and [ADR-0004](adr/ADR-0004-playbook-dsl-versus-external-orchestration-frameworks.md) for the design rationale.
