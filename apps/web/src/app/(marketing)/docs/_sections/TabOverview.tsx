import { Code, Pre, SectionHeading, SubHeading } from "./shared"

// ── Tab content components ─────────────────────────────────────────────────────

export function TabOverview() {
  return (
    <div className="space-y-16">
      <section id="try-in-60-seconds">
        <div className="rounded-2xl border border-indigo-200 bg-indigo-50/60 px-6 py-5">
          <p className="text-xs uppercase tracking-wide text-indigo-700 font-semibold mb-2">Try Conduct in 60 seconds</p>
          <h2 className="text-lg font-bold text-stone-900 mb-3">Zero local install. Point any Anthropic SDK at the hosted Guard proxy.</h2>
          <Pre>{`curl -fsSL conductai.ai/install | sh`}</Pre>
          <p className="text-sm text-stone-600 mt-3">
            Prompts for email + company, provisions a 7-day trial workspace, drops <Code>~/.conduct/env</Code> with a trial token for Anthropic + OpenAI, and prints a magic-link URL to sign into the dashboard.{" "}
            <a href="/docs?tab=getting-started#quick-trial" className="text-indigo-600 hover:underline font-medium">Full walkthrough →</a>
          </p>
          <p className="text-xs text-stone-500 mt-2">
            Trial cap: 200 requests/day shared across providers. Perplexity / Bedrock / others: same proxy, same policy — bring your own vendor key in Settings → Environments.
          </p>
        </div>
      </section>

      <section id="how-it-works">
        <h1 className="text-3xl font-bold text-stone-900 mb-3">How Conduct works</h1>
        <p className="text-stone-600 leading-relaxed text-base mb-10">
          Workflows are Conduct&apos;s governed response layer. When Guard or an alert detects something, a
          playbook responds: it investigates, proposes a specific action, waits for a human to approve that
          action, and records the evidence. Runs start from a webhook, on a schedule, or on demand. Every run is traced, every outcome is recorded.
        </p>
        <div className="space-y-0">
          {[
            { step: "1", title: "Playbook",  body: "A YAML file that defines what an agent does, its blocks (AI reasoning, tool calls, approval gates), its triggers, and its inputs. Playbooks live in the Conduct registry and can be customized.", detail: "Each block is typed: brain (LLM reasoning), tool_call (GitHub, Slack, Linear), approval (human gate), or condition (branching logic). The graph is editable on the canvas." },
            { step: "2", title: "Install",   body: "Installing a playbook creates a workflow in your workspace. Conduct generates the agent graph, registers any GitHub webhooks, and stores the resolved inputs. No code to write.", detail: "Under the hood: a WorkflowVersion record is created from the playbook YAML. The YAML is interpreted at install time, the canvas shows the live graph." },
            { step: "3", title: "Configure", body: "Assign an environment to the agent. An environment holds your credentials (GitHub PAT, Slack token, Linear key, LLM API key). One environment can be shared across many agents.", detail: "Credentials are encrypted with AES-256-GCM before storage. They are decrypted in-process at runtime, scoped to the agent's workspace, and never returned to the client." },
            { step: "4", title: "Run",       body: "A run is created by a trigger: a GitHub webhook (pull_request, issues), a schedule (cron), a manual click in the UI, or a POST to the API. Runs execute the graph block by block.", detail: "The executor advances one block at a time. If a block hits an approval gate, the run is paused and waits for a human decision before proceeding." },
            { step: "5", title: "Trace",     body: "Every run streams live events: block_started, brain_tool_call, block_completed, run_paused. The run detail page shows the full trace in real time via Server-Sent Events.", detail: "Events are written to run_events and are immutable. You can replay any run's trace after the fact, nothing is discarded." },
            { step: "6", title: "Outcome",   body: "When a run completes, Conduct writes a semantic outcome: incident_investigated, release_tagged, pr_opened. Outcomes power the Dashboard metrics.", detail: "The outcome is derived from the playbook slug and the run's state. Pre-outcome runs use heuristic fallback, historical counts never drop." },
            { step: "7", title: "Audit",     body: "Every tool call, decision, and output is in the run_events log. The audit trail is immutable and workspace-scoped, you can always answer 'what did the agent do and why?'", detail: "Run events include the full payload for each action: the GitHub API call, the PR number opened, the Slack message sent. Nothing is summarized away." },
          ].map(({ step, title, body, detail }) => (
            <div key={step} className="flex gap-6 pb-8 relative">
              <div className="flex flex-col items-center">
                <div className="w-8 h-8 rounded-full bg-stone-900 text-white text-sm font-bold flex items-center justify-center shrink-0 z-10">{step}</div>
                {parseInt(step) < 7 && <div className="w-px flex-1 bg-stone-200 mt-2" />}
              </div>
              <div className="pt-1 pb-2">
                <p className="font-semibold text-stone-900 mb-1">{title}</p>
                <p className="text-sm text-stone-600 leading-relaxed mb-2">{body}</p>
                <p className="text-xs text-stone-400 leading-relaxed">{detail}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section id="threat-model">
        <SectionHeading id="threat-model">Security & threat model</SectionHeading>
        <p className="text-stone-500 text-sm mb-6">
          What Conduct protects today, what it does not, and where we're headed.
          We believe you deserve an honest answer to "is it safe to give this agent my GitHub token?"
        </p>

        <SubHeading>What we protect</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            { label: "Credentials encrypted at rest",    detail: "Every secret is encrypted with AES-256-GCM before writing to the database. The encryption key is an env var, never stored alongside the ciphertext." },
            { label: "Workspace isolation",              detail: "Every query is scoped to workspace_id. A credential, agent, or run from workspace A is never accessible to workspace B, enforced at the ORM layer on every request." },
            { label: "Human approval gates",             detail: "Any block can be marked as an approval gate. The run pauses and cannot proceed until an authorized user approves or rejects." },
            { label: "Immutable audit log",              detail: "run_events are append-only. Every tool call, LLM decision, and output is recorded with a timestamp. There is no delete path for run events." },
            { label: "HMAC-validated webhooks",          detail: "GitHub webhook payloads are validated with HMAC-SHA256 before the run is created. Unauthenticated payloads are rejected with 401." },
            { label: "Hashed API keys",                  detail: "API keys are SHA-256 hashed before storage. The plaintext is shown once at creation and never stored. A compromised database does not expose working keys." },
          ].map(({ label, detail }) => (
            <div key={label} className="px-4 py-3">
              <p className="font-medium text-stone-800 mb-0.5">{label}</p>
              <p className="text-stone-500 text-xs leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>

        <SubHeading>What we do not protect (yet)</SubHeading>
        <div className="rounded-xl border border-amber-200 bg-amber-50 divide-y divide-amber-100 text-sm mb-6">
          {[
            { label: "Credential mediation",             detail: "Credentials are decrypted and passed to the executor at runtime. The executor sees the plaintext token. A compromised executor process could exfiltrate it. Mitigation: the executor runs server-side, not client-side." },
            { label: "Network egress allowlist",         detail: "Agents can call any external URL during a run. There is no per-environment allowlist today. A misconfigured or malicious playbook could make arbitrary outbound requests." },
            { label: "Runtime isolation",                detail: "Some blocks execute in the API worker while sandbox-backed execution can run in workspace-scoped environments. Treat sandbox isolation as a configured runtime property, not a blanket guarantee." },
            { label: "Playbook static analysis",         detail: "Conduct does not analyze a playbook's tool calls before you install it. You should review the YAML before installing third-party or custom playbooks." },
          ].map(({ label, detail }) => (
            <div key={label} className="px-4 py-3">
              <p className="font-medium text-amber-900 mb-0.5">{label}</p>
              <p className="text-amber-800 text-xs leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>

        <SubHeading>Long-term direction</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-4">
          {[
            ["Credential proxy",              "Agents call a proxy that holds the token, the executor never sees plaintext. Revocation and rate-limiting become centralizable."],
            ["Egress allowlist per environment","Each environment declares which hostnames agents are allowed to call. Requests outside the allowlist are rejected before execution."],
            ["Per-block process isolation",   "Every execution path gets isolated at the process or sandbox boundary. A crashing block cannot affect others."],
            ["Playbook supply chain analysis","Static analysis of YAML before install: what tools are called, what data is read, what external endpoints are contacted."],
          ].map(([label, detail]) => (
            <div key={label} className="flex gap-4 px-4 py-3">
              <span className="font-medium text-stone-700 w-48 shrink-0">{label}</span>
              <span className="text-stone-500 text-xs leading-relaxed">{detail}</span>
            </div>
          ))}
        </div>

        <div className="rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-600">
          <strong>Questions or concerns?</strong> Email <a href="mailto:security@conductai.ai" className="text-indigo-600 hover:underline">security@conductai.ai</a>.
        </div>
      </section>

      <section id="action-tools" className="scroll-mt-8">
        <SectionHeading id="action-tools">Gating agent actions</SectionHeading>
        <p className="text-stone-600 leading-relaxed mb-4">
          When an agent calls a tool that takes a real action (refund, cancel, update, send, delete), Guard
          evaluates the call against the current policy before the action runs. Warn hands off to a human.
          Block returns a clean refusal. Every decision lands in the same hash-chained audit as your model calls.
        </p>
        <p className="text-stone-600 leading-relaxed mb-4">
          Rules are declarative YAML. Ship a rule without a deploy. Below is a minimal example that caps a
          support agent&apos;s refunds and requires supervisor review above a threshold.
        </p>
        <Pre>{`# ~/.conductguard/policies/refund-cap.yaml
name: refund-cap
applies_to:
  - "tool:issue_refund"
rules:
  - id: block-over-1000
    when:
      arg.amount_usd: { gt: 1000 }
    action: block
    reason: "Refund exceeds hard cap. Route to finance."

  - id: warn-over-2x-dispute
    when:
      arg.amount_usd: { gt: "\${arg.disputed_amount_usd} * 2" }
    action: warn
    handoff: supervisor
    reason: "Refund is more than twice the disputed amount. Supervisor review required."`}</Pre>
        <p className="text-stone-500 text-sm mt-4">
          The same pattern applies to any action tool: cancellation reason lists, pricing commitments, DB writes,
          outbound sends. See{" "}
          <a href="?tab=guard#guard-policy-reference" className="text-indigo-600 hover:underline">Policy reference</a>{" "}
          for the full rule grammar.
        </p>
      </section>
      <section id="cedar-import" className="scroll-mt-8">
        <SectionHeading id="cedar-import">Cedar policy import</SectionHeading>
        <p className="text-stone-600 leading-relaxed mb-4">
          Guard accepts policies in <a href="https://www.cedarpolicy.com/" target="_blank" rel="noopener" className="text-indigo-600 hover:underline">Cedar</a>,
          the AWS-blessed open standard used by AWS Verified Permissions and (via Dogwood)
          Amazon Bedrock AgentCore. Import Cedar policies from your existing IAM stack, and
          Guard converts them to its native pack format. Runtime evaluation is unchanged.
        </p>
        <SubHeading>CLI import</SubHeading>
        <Pre>{`# Preview
conduct import-cedar my-policy.json \\
  --pack-slug my-cedar-import \\
  --pack-name "My Cedar Import"

# Install
conduct import-cedar my-policy.json \\
  --pack-slug my-cedar-import \\
  --pack-name "My Cedar Import" \\
  --install`}</Pre>
        <SubHeading>Cedar text export</SubHeading>
        <p className="text-stone-500 text-sm mb-3">
          Every installed pack renders as Cedar text syntax for readability. Click{" "}
          <strong>View as Cedar</strong> on any pack detail page in the Registry, or fetch
          it via the API:
        </p>
        <Pre>{`GET /guard/registry/packs/{slug}/cedar
GET /guard/registry/packs/{slug}/cedar?version=2.2.0`}</Pre>
        <p className="text-stone-500 text-sm mt-3">
          See the{" "}
          <a href="https://github.com/sseshachala/conductai/blob/main/docs/cedar-adapter-usage.md" className="text-indigo-600 hover:underline">
            full Cedar adapter user guide
          </a>{" "}
          for the mapping table, error taxonomy, and runnable examples.
        </p>
      </section>
    </div>
  )
}
