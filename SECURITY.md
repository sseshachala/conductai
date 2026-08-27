# SECURITY

Conduct AI is a policy enforcement layer for AI agents.
It enforces one policy engine across LLM proxy calls and MCP tool calls, and writes a hash-chained audit log per workspace.

This document covers supported versions, private vulnerability reporting, disclosure expectations, safe harbor, and scope.

## Supported versions

Conduct maintains security fixes on active development lines.

| Release line | Security support status | Notes |
| --- | --- | --- |
| `main` (latest commit) | ✅ Active | Primary location for security fixes. |
| Latest tagged minor release on each active major | ✅ Active | Critical/high security fixes may be backported when feasible. |
| Older minors within the same major | ⚠️ Best effort only | Upgrade to latest minor in that major first. |
| End-of-life majors | ❌ Not supported | No security patches. |

If your deployment cannot upgrade quickly, open a private report and include your pinned version so maintainers can confirm backport feasibility.

## How to report a vulnerability (private)

- **Preferred channel:** `security@conductai.ai`  
- **Maintainer placeholder (replace if needed):** `TODO: set security contact for this repository`

Do **not** open public issues, discussions, or pull requests containing exploit details.

### Include this in your report

1. Affected component and surface (proxy or MCP).
2. Version/commit (`git sha`, image tag, or release tag).
3. Reproduction steps and required configuration.
4. Expected behavior vs. observed behavior.
5. Impact assessment (data exposure, policy bypass, integrity, availability).
6. Any logs, request/response samples, or PoC artifacts (redacted as needed).

### Response SLAs

- **Acknowledgment:** within **2 business days**.
- **Triage update:** within **5 business days**.
- **Ongoing status updates:** at least every **7 calendar days** until resolution/disclosure.

If the report is incomplete, maintainers may request more detail before severity and timeline commitments are final.

## Coordinated disclosure policy

We follow coordinated disclosure:

1. Reporter shares details privately.
2. Maintainers validate impact and propose remediation timeline.
3. Reporter and maintainers coordinate a disclosure date.
4. Public advisory is published after fix availability (or mitigation guidance when a fix is delayed).

Please avoid public disclosure before coordinated release unless there is an immediate, active exploitation risk and maintainers are unresponsive.

## Safe harbor

If you act in good faith under this policy, Conduct maintainers will not pursue action for accidental policy violations while testing:

- Research stays within systems/accounts you own or are explicitly authorized to test.
- You avoid privacy violations, data destruction, service degradation, or persistence.
- You do not exfiltrate secrets or user data beyond what is minimally necessary to demonstrate impact.
- You stop and report promptly after confirming a finding.

This safe harbor does **not** grant permission to test third-party infrastructure, social engineer users, or perform disruptive denial-of-service activity.

## In-scope components

Security reports are in scope for:

- LLM proxy surface (`/proxy/{provider}/v1/*` family and provider-specific proxy handlers).
- LiteLLM guard plugin integration (`conduct-litellm-guard`).
- MCP server/fronting behavior, including `guard_check` before tool calls.
- Policy engine evaluation and enforcement behavior.
- Hash-chained audit log integrity (`prev_hash`/`entry_hash` invariants).
- Approvals/HITL flows and approval state handling.

Out-of-scope examples: vulnerabilities in upstream model providers, unmanaged third-party MCP tools themselves, and unsupported/end-of-life Conduct versions.
