import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Governing 37 AI Agents in Production: A Field Guide to Runtime Governance | Conduct",
  description:
    "Policy as a runtime primitive, not a doc. How ConductGuard governs LLM calls, tool calls, budgets, and approvals across every AI agent your team runs.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Field Guide
          </span>
          <span className="text-xs text-stone-400">August 20, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          Governing 37 AI Agents in Production: A Field Guide to Runtime Governance
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          One identity, one policy, one audit trail across every AI agent your team runs.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">

        <img
          src="/blog/governing-37-ai-agents-hero.png"
          alt="Governing 37 AI Agents in Production — a field guide to runtime governance"
          className="w-full rounded-2xl border border-stone-200 mb-12"
        />

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The problem we started with</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          At most engineering teams we talk to, AI now runs unattended in five
          places at once. Claude Code writes PRs. Cursor edits files. Copilot
          suggests completions. Custom agents run scheduled tasks. An MCP server
          exposes tools to any AI client on the network. Each one has its own
          dashboard, its own budget, its own audit surface.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          None of them talk to each other. Nobody in the room can answer basic
          questions:
        </p>
        <ul className="list-disc list-inside text-stone-700 leading-relaxed mb-4 space-y-1">
          <li>What did AI do in production this week?</li>
          <li>Which model got called by which agent for which task?</li>
          <li>Did the compliance rule we wrote in Notion actually apply to that Cursor session?</li>
          <li>Who approved that deploy?</li>
        </ul>
        <p className="text-stone-700 leading-relaxed mb-4">
          The AI-safety conversation still lives in Google Docs. The AI-usage
          reality is a proliferation of tools nobody governs.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          We built ConductAI to make policy something you enforce at runtime,
          not something you write in a doc and hope people follow.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What ConductAI actually is</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Three layers, one platform:
        </p>
        <ol className="list-decimal list-inside text-stone-700 leading-relaxed mb-4 space-y-2">
          <li>
            <strong>ConductGuard</strong> is the policy and audit spine. A proxy
            sits in front of every LLM call. An MCP server sits in front of
            every tool call. Every request runs through a declarative rule
            engine before it goes anywhere. Every decision writes a signed
            audit event with lineage.
          </li>
          <li>
            <strong>Playbook Runtime</strong> is 37 pre-built YAML playbooks
            that do specific engineering work (PR reviews, incident response,
            security scans, release ops). Runs inside Guard so every LLM call
            and tool call it makes is governed by the same policies.
          </li>
          <li>
            <strong>Compliance Packs and Marketplace</strong> ship 10 packs
            mapped to real regulatory frameworks (SOC 2 CC6.6, HIPAA
            §164.312, EU AI Act Article 15). Install one, get 20-40 policy
            rules pre-configured.
          </li>
        </ol>
        <p className="text-stone-700 leading-relaxed mb-6">
          The value proposition is one identity, one policy, one audit trail
          across every AI agent your team uses.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Six use cases, from what real teams are doing</h2>

        <h3 className="text-xl font-bold text-stone-900 mt-8 mb-3">1. PR reviewer that can never merge</h3>
        <p className="text-stone-700 leading-relaxed mb-4">
          Playbook: <code>pr-reviewer.yaml</code> (223 lines, ships in the repo).
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>Setup:</strong> Install the playbook. Register a GitHub
          webhook. Assign a <code>cond_agt_pr-reviewer</code> token with
          read+comment scope on your repo. Install the{" "}
          <code>conduct-endpoint-attacks</code> skill pack (PII/secret leak
          detection). Set a $2/PR budget cap.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>What it does at runtime:</strong> When a PR opens, the agent
          reads the diff, comments on style and security issues, requests
          changes. When it tries to comment, Guard evaluates every LLM call
          and every GitHub API call against the installed rules. It scrubs
          secrets before commenting. It can never merge, because the token
          doesn&apos;t have merge scope and a Guard rule blocks the{" "}
          <code>github.pull.merge</code> tool regardless.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          <strong>What compliance sees:</strong> every decision this agent made
          in the last 90 days, signed and hash-chained. Which rule fired, what
          the prompt was, what the model output was, how much it cost.
        </p>

        <h3 className="text-xl font-bold text-stone-900 mt-8 mb-3">2. Incident responder with a human gate</h3>
        <p className="text-stone-700 leading-relaxed mb-4">
          Playbook: <code>incident-responder.yaml</code>.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>Setup:</strong> PagerDuty webhook triggers the playbook.
          Install the <code>conduct-base</code> and{" "}
          <code>conduct-network-ops</code> packs. Set the agent identity to
          read-only IAM. Configure a Slack channel for approvals.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>What it does at runtime:</strong> When an alert fires, the
          agent correlates recent commits and deployments, formulates a
          hypothesis, and posts it to Slack. If it wants to suggest a
          rollback, the Guard approval action fires. Nothing executes until a
          human clicks Approve in Slack. The approval decision is recorded
          with the approver&apos;s identity, timestamp, and reason.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          <strong>Why this matters:</strong> the wedge between &ldquo;AI
          suggests&rdquo; and &ldquo;AI acts&rdquo; is where all the risk
          lives. Approval gates turn suggestion into a reviewed decision
          without slowing anyone down.
        </p>

        <h3 className="text-xl font-bold text-stone-900 mt-8 mb-3">3. SOC 2 evidence gathering, hands-free</h3>
        <p className="text-stone-700 leading-relaxed mb-4">
          Playbook: <code>ai-output-auditor.yaml</code> combined with{" "}
          <code>security-scanner.yaml</code>.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>Setup:</strong> Install the <code>conduct-iso-42001</code>{" "}
          and <code>conduct-nist-ai-rmf</code> packs (both map to SOC 2 CC6,
          CC7, CC8 controls). Assign a read-only cloud IAM token. Schedule the
          playbook weekly.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>What it does at runtime:</strong> The agent pulls current
          IAM policies, encryption states, access logs, and MFA enforcement
          across your cloud accounts. Compares against the installed
          compliance rules. Writes a findings report with clause-by-clause
          evidence. Every LLM call is bounded to a $50 budget, and every
          finding is written to the hash-chained ledger.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          <strong>What the auditor sees:</strong> a report that references
          specific SOC 2 clauses, specific findings, specific evidence
          timestamps. All signed. The rule that flagged each finding is
          traceable to the pack version installed at scan time.
        </p>

        <h3 className="text-xl font-bold text-stone-900 mt-8 mb-3">4. Runaway spend prevention (shipped this month)</h3>
        <p className="text-stone-700 leading-relaxed mb-4">
          Every AI-serious team has had this happen: an agent gets stuck in a
          retry loop and burns hundreds of dollars in an hour. Or a leaked API
          key generates a $50K bill before anyone notices.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>What ConductGuard now does:</strong> every LLM call runs
          through a pre-forward budget check. If the workspace has spent past
          the monthly hard cap, the request returns HTTP 429 with{" "}
          <code>{`{"error": {"type": "guard_budget_exceeded", ...}}`}</code>{" "}
          before touching the provider. Zero cost overshoot from that call.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>Rate limits at the same layer:</strong> admins can set
          requests-per-minute and tokens-per-minute caps per workspace or per
          agent identity. Same 429 response,{" "}
          <code>{`{"type": "guard_rate_limited", "metric": "rpm", "limit": 60, "current": 61}`}</code>. The agent sees a structured error and can back off.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          <strong>Where it plugs in:</strong> every proxy call, no exceptions.
          Any AI tool pointed at Guard is bounded by these caps, whether
          it&apos;s Claude Code, a custom Python agent, or a scheduled cron
          job.
        </p>

        <h3 className="text-xl font-bold text-stone-900 mt-8 mb-3">5. Security scanning with auto-remediation</h3>
        <p className="text-stone-700 leading-relaxed mb-4">
          Playbooks: <code>security-scanner.yaml</code> (386 lines) and{" "}
          <code>security-autopilot-fix.yaml</code>.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>Setup:</strong> Install both playbooks. Install the{" "}
          <code>conduct-endpoint-attacks</code> pack. Assign a{" "}
          <code>cond_agt_security-scanner</code> token with issue-create and
          PR-open scope, but no merge scope.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>What it does at runtime:</strong> The scanner walks repos
          looking for OWASP top-10 patterns, exposed secrets in git history,
          dependency vulnerabilities. It opens GitHub issues (not PRs) with
          specific line references. If a companion{" "}
          <code>security-autopilot-fix</code> is enabled for a repo, it picks
          up the issue, sandboxes an attempt at a fix in an ephemeral
          container, runs the tests, and opens a draft PR. A human still
          merges.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          <strong>Why sandbox execution:</strong> the security agent runs
          code. It runs it in Modal or E2B ephemeral containers with no
          persistent access to production. When the run finishes, the
          container is destroyed.
        </p>

        <h3 className="text-xl font-bold text-stone-900 mt-8 mb-3">6. Network diagnosis from an alert</h3>
        <p className="text-stone-700 leading-relaxed mb-4">
          Playbook: <code>network-diagnosis-agent.yaml</code> (264 lines).
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>Setup:</strong> Alert webhook triggers the playbook. Install
          the <code>conduct-network-ops</code> pack. Assign a network
          operations agent identity bounded to sandboxed shell only.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>What it does at runtime:</strong> The agent runs{" "}
          <code>dig</code>, <code>traceroute</code>, <code>curl</code>, and
          BGP-check scripts against the affected service. Never runs a
          mutation. Posts findings to Slack. If it wants to suggest a config
          change, an approval gate fires. Every shell command is logged with
          input, output, and duration in the audit ledger.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          <strong>Why bound to read-only:</strong> the{" "}
          <code>conduct-network-ops</code> pack blocks any policy-modify or
          config-mutate tool at the Guard layer. Even if the agent were
          prompt-injected into trying, Guard would block the call before it
          left the sandbox.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What makes this different from every other AI tool</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>Policy is a runtime primitive, not a config toggle.</strong>{" "}
          The rule that says &ldquo;PR reviewer can never merge&rdquo; is a
          declarative YAML rule evaluated on every request. It&apos;s
          version-controlled. It&apos;s signed. It&apos;s audited when it
          fires. Changing it requires a new signed version, not editing a
          checkbox.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>Hash-chained audit ledger.</strong> Every decision writes a
          row with <code>prev_hash → entry_hash</code>. Tampering with one row
          breaks the whole chain, and every row after it is invalidated.
          Compliance can prove the audit trail hasn&apos;t been edited.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>Per-agent identity is a first-class token type.</strong>{" "}
          <code>cond_agt_*</code> tokens carry an expiry, a scope, and a
          lineage. When an agent makes a call, the audit ledger records which
          identity called, what scope it had, what token was in use. Not a
          per-user API key repurposed for a robot.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>Compliance packs mapped to real clauses.</strong> SOC 2
          CC6.6, HIPAA §164.312(b), EU AI Act Article 15, SR 11-7 model risk
          management. Not &ldquo;safety&rdquo; or &ldquo;pci&rdquo; as
          one-word presets. Auditors get clause-by-clause evidence.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          <strong>Human approval workflow with rich context.</strong> When a
          Guard rule triggers approval, the request pauses. A Slack message
          with the full context (agent identity, prompt summary, tool it wants
          to call, historical spend, run linkage) goes to the approval group.
          One click resumes or rejects, and the decision writes to the audit
          ledger with the approver&apos;s identity.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          <strong>Playbook runtime and Guard, built together.</strong> Guard
          sits inside every brain block. When a playbook makes an LLM call,
          that call is governed. When a playbook invokes a tool, that tool
          call is governed. There&apos;s no gap between &ldquo;the playbook
          does something&rdquo; and &ldquo;governance sees it.&rdquo;
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Provider coverage</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Three native adapters (Anthropic, OpenAI, Perplexity). Six gateway
          adapters (OpenRouter, Portkey, Helicone, LiteLLM, Azure OpenAI,
          ConductAI) auto-detected from the upstream URL. Transitively reaches
          400+ models across every major provider: Bedrock, Vertex AI, Gemini,
          Cohere, Mistral, Groq, Together, Fireworks, DeepSeek, xAI, and any
          OSS server hosted via OpenRouter or self-hosted LiteLLM.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          The gateway adapter pattern means if your team already runs an LLM
          gateway, Guard governs on top of it. If you don&apos;t, use
          ConductAI direct. Either way, one policy engine, one audit ledger.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Getting started</h2>
        <pre className="bg-stone-900 text-stone-100 text-sm rounded-lg p-4 overflow-x-auto mb-4"><code>{`pip install conduct-cli
conduct login
conduct guard install       # wires the hook into Claude Code / Cursor
conduct run pr-reviewer --repo owner/name --pr 42
conduct verify <run-id>`}</code></pre>
        <p className="text-stone-700 leading-relaxed mb-4">
          For the proxy path:
        </p>
        <pre className="bg-stone-900 text-stone-100 text-sm rounded-lg p-4 overflow-x-auto mb-4"><code>{`export ANTHROPIC_BASE_URL="https://api.conductai.ai/proxy/anthropic"
export OPENAI_BASE_URL="https://api.conductai.ai/proxy/openai/v1"`}</code></pre>
        <p className="text-stone-700 leading-relaxed mb-6">
          Every SDK call from now on runs through Guard. Every playbook
          invocation runs through Guard. Every tool call runs through Guard.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What&apos;s next</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Second half of 2026, we&apos;re focused on three things:
        </p>
        <ol className="list-decimal list-inside text-stone-700 leading-relaxed mb-4 space-y-2">
          <li>
            <strong>Mid-stream enforcement.</strong> Cut streaming responses
            the moment a budget cap fires, not after the stream completes.
          </li>
          <li>
            <strong>Behavioral risk scoring on agent identity.</strong>{" "}
            Persistent risk score per <code>cond_agt_*</code> with quarantine
            and decay.
          </li>
          <li>
            <strong>Native Bedrock adapter.</strong> The one provider Fortune
            500 compliance teams require direct-native rather than via
            gateway.
          </li>
        </ol>
        <p className="text-stone-700 leading-relaxed mb-6">
          The platform is MIT licensed and self-hostable. If you&apos;re
          running AI agents in production and want to govern them the way you
          govern the rest of your stack, we&apos;d like to hear from you.
        </p>

        <div className="mt-12 border-t border-stone-100 pt-8">
          <CtaLink className="rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors" />
        </div>

      </div>
    </article>
  )
}
