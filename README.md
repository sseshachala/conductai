<div align="center">

[![Try Conduct — conductai.ai](https://img.shields.io/badge/Try_Conduct-conductai.ai-6366f1?style=for-the-badge&logoColor=white&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0xMiAyQzYuNDggMiAyIDYuNDggMiAxMnM0LjQ4IDEwIDEwIDEwIDEwLTQuNDggMTAtMTBTMTcuNTIgMiAxMiAyek0xMSAxN3YtNkg5bDMtNCAzIDRoLTJ2NmgtMnoiLz48L3N2Zz4=)](https://conductai.ai)
[![Star on GitHub](https://img.shields.io/github/stars/sseshachala/conductai?style=for-the-badge&logo=github&color=gold)](https://github.com/sseshachala/conductai/stargazers)
[![License Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue?style=for-the-badge)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/conduct-cli?style=for-the-badge&logo=pypi&logoColor=white&color=0073b7)](https://pypi.org/project/conduct-cli/)

# Conduct

**Runtime governance for AI agents — one policy enforces across every LLM call, every shell tool, every teammate's AI session.**

![Conduct — live run trace showing agent executing an issue-to-PR agent template](apps/web/public/guard-docs/dashboard.png)

</div>

---

## Ask Lens — natural language over your governance data

**Lens** is Conduct's chat surface. It sits above every workspace as a Guard-enforced assistant — ask about blocked events, approvals, spend, rules, agent activity in plain English. Every tool call the assistant makes runs through Guard: same policy engine, same audit trail as a live agent.

![Lens chat — asking "how many guard blocks today", grounded in real audit data](apps/web/public/guard-docs/lens-chat.png)

- **One chat for the whole platform.** Guard, workflows, rules, compliance — one input, no context switching.
- **Grounded in your data.** Not a wrapper around ChatGPT. Every answer comes from your workspace's audit log, policy state, and run history.
- **Guard-enforced.** Lens's LLM calls go through the same policy engine as your agents. Same rules, same limits, same audit chain.
- **Drilldowns built in.** Ask "who got blocked today" — get a table with per-row links to the full audit record.

Two product surfaces, one repo, one policy:

- **Conduct Guard** — the policy engine. Decides `block / warn / audit / inject` for every AI action **before** it executes, backed by signed configuration and a hash-chained audit log.
- **Conduct Router** — the LLM proxy. Point any provider SDK (Anthropic, OpenAI, Perplexity) at Router and every request runs through Guard on the way to the upstream provider.

---

## Governance, not observability

Runtime firewalls like [Straiker](https://www.straiker.ai/) and [Lakera](https://www.lakera.ai/) tell you what an agent **did**. Guard controls what an agent **can do** — with cryptographic proof.

|                        | Runtime firewalls          | Conduct Guard              |
|------------------------|----------------------------|----------------------------|
| Timing                 | After the action           | **Before** the action      |
| Config integrity       | Trust the pack             | **Workspace-signed**       |
| Audit                  | Log stream                 | **SHA-256 hash chain**     |
| Coverage               | LLM calls only             | LLM **and** shell / MCP    |
| Failure mode           | Fail-open (soft)           | **Fail-closed** by default |

**The three-pillar moat:**

1. **Signed configuration** — every workspace signs its active policy set. Every Guard check verifies the signature before enforcing. A tampered pack — pushed by anyone, at any layer — is rejected before it can decide anything.
2. **Hash-chained audit** — every decision appends to a SHA-256 chain rooted at workspace genesis. Any missing or altered entry breaks the chain and is caught on one-click verification. Evidence you can hand to an auditor.
3. **Policy-first, not detection-first** — rules decide before the action executes, with structured reasons. Not anomaly detection after the fact.

## Discovery — the free wedge

New here? Start with **Discovery mode**: read-only visibility into every AI action your team takes for 14 days. No policy to author, nothing to install upstream, no cost. When you're ready to enforce, promote a rule from what Discovery already saw.

→ [conductai.ai/sign-up](https://conductai.ai/sign-up)

---

## Quick start

```bash
git clone https://github.com/sseshachala/conductai
cd conductai
docker compose up
```

- API on `http://localhost:8000` (Guard + Router live at `/guard/*` and `/proxy/*`)
- Canvas UI on `http://localhost:3000`
- Redis worker + Postgres come up in the same stack

Point any provider SDK at Router:

```bash
curl https://api.conductai.ai/proxy/anthropic/v1/messages \
  -H "Authorization: Bearer cond_agt_..." \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":1024,"messages":[{"role":"user","content":"Hello"}]}'
```

Or wrap your CLI hooks with Guard:

```bash
pip install conduct-cli
conduct login
conduct sync        # installs hook + MCP, pulls policies
```

Now every Claude Code, Cursor, Copilot, ChatGPT, or Codex session on that machine is governed by the same active packs.

---

## What ships in this repo

| Component               | Path                                          |
|-------------------------|-----------------------------------------------|
| **Guard runtime**       | `apps/api/app/modules/guard/`                 |
| **Router (proxy)**      | `apps/api/app/modules/guard/routers/proxy.py` |
| **Compliance packs**    | `apps/api/app/modules/guard/skill_packs/`     |
| **Canvas UI**           | `apps/web/`                                   |
| **Playbook DSL loader** | `apps/api/app/dsl/`                           |
| **Playbook library**    | `apps/api/playbooks/` (22 pre-built)          |
| **CLI**                 | `packages/conduct-cli/`                       |

**20+ compliance packs ship out of the box:** OWASP, SOC 2 CC7.3, HIPAA §164.312, PCI DSS 4.0, EU AI Act Art. 15/16, NIST AI RMF, ISO 42001, and framework-specific packs for Python, Node, and Terraform.

**22 pre-built playbooks:** Issue → PR, code review, incident response, prod deploy gate, CI/CD triage, security scanner triage, Slack digest, and more. Each is one YAML file; edit-and-run.

---

## Architecture at a glance

```
   Developer / agent                     Guard control plane
   ─────────────────                     ───────────────────
   Claude Code   ──┐                     ┌── Canvas UI (Next.js)
   Cursor        ──┤   CLI hook  ────►   ├── FastAPI + policy engine
   Copilot       ──┤   (cond_cli)        ├── Postgres (state, audit)
   Codex         ──┘                     ├── Redis (workers, queues)
                     ┌──── MCP  ────►    └── Hash chain (SHA-256)
   Any SDK       ────┤
   (Anthropic,       └── Router ────►    Upstream provider (Anthropic,
    OpenAI,             /proxy/*         OpenAI, Perplexity, ...)
    Perplexity)
```

Guard checks fire at three chokepoints:

- **CLI hook** — every Claude Code / Cursor / Copilot / Codex tool call.
- **MCP layer** — every MCP tool invocation.
- **Router** — every LLM call by any SDK.

One policy, three enforcement surfaces.

---

## Deployment

- **Self-host with docker compose** — the command above. Runs everything locally.
- **Self-host on Kubernetes** — deployment templates ship in [issue #1149](https://github.com/sseshachala/conductai/issues/1149).
- **Hosted** — [conductai.ai](https://conductai.ai). Free tier includes Discovery; paid tiers unlock enforcement + Router + hash-chain verification API.

---

## Security & Trust

- [SECURITY.md](./SECURITY.md) — vulnerability reporting policy, scope, coordinated disclosure, and safe harbor.
- [Threat model](./docs/threat-model.md) — system context, trust boundaries, attacker goals, mitigations, and residual risks.
- [Policy decision contract](./docs/policy-decision-contract.md) — `guard_check` decision semantics and fail-mode behavior.
- [Audit log verification](./docs/audit-log-verification.md) — independent `prev_hash`/`entry_hash` chain verification procedure and example script.
- [API versioning](./docs/api-versioning.md) — proxy/MCP compatibility, deprecation windows, and OpenAPI publication guidance.

---

## License

**[Apache License 2.0](./LICENSE)** — the entire repository, including the CLI, Guard, Router, Agent Booster, playbooks, and packs.

- Free for commercial and non-commercial use, modification, and redistribution.
- Includes an explicit patent grant from all contributors (Apache 2.0 §3).
- Trademark rights are not granted; see [NOTICE](./NOTICE) — "Conduct", "Conduct AI", and "Conduct Guard" remain trademarks of Conduct AI.
- Redistribution must preserve the `LICENSE` and `NOTICE` files.

The hosted control plane at [conductai.ai](https://conductai.ai) (canvas UI, team RBAC, marketplace, managed Guard) is a commercial offering built on top of this repository.

For enterprise support, indemnification, or licensing questions, email **hello@conductai.ai**.

---

## Contributing

We accept bug reports, docs fixes, new playbooks, new packs, tests, and code. Read [CONTRIBUTING.md](./CONTRIBUTING.md) first.

- Everyone participating agrees to the [Code of Conduct](./CODE_OF_CONDUCT.md).
- Security vulnerabilities: don't open a public issue. See [SECURITY.md](./SECURITY.md).
- Anything else: [GitHub Discussions](https://github.com/sseshachala/conductai/discussions) or [SUPPORT.md](./SUPPORT.md).

## Links

- **Product:** [conductai.ai](https://conductai.ai)
- **Guard landing:** [conductai.ai/guard](https://conductai.ai/guard)
- **Router landing:** [conductai.ai/router](https://conductai.ai/router)
- **Docs:** [conductai.ai/docs](https://conductai.ai/docs)
- **Discussions:** [github.com/sseshachala/conductai/discussions](https://github.com/sseshachala/conductai/discussions)
- **Changelog:** [CHANGELOG.md](./CHANGELOG.md) + [Releases](https://github.com/sseshachala/conductai/releases)
- **Book a demo:** [cal.com/sudhi-seshachala-pks7pd](https://cal.com/sudhi-seshachala-pks7pd)

> **⭐ If Conduct saves your team time, [star it](https://github.com/sseshachala/conductai/stargazers) — it helps other teams find it.**
