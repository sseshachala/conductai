import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Use cases we operate in today | Conduct",
  description:
    "Nine shipped surfaces of Guard, the all-in-one AI compliance and security platform. IDE governance, MCP governance, security loop, compliance evidence, spend guardrails, shadow-AI discovery, agent identity, content inspection, and business-agent action governance.",
}

type UseCase = {
  n: string
  slug: string
  title: string
  oneLiner: string
  persona: string
  situation: string
  mechanics: string[]
  scenario: string
  metrics: string
  integrations: string
  ctaLabel: string
  ctaHref: string
  note?: string
}

const CASES: UseCase[] = [
  {
    n: "01",
    slug: "ide-governance",
    title: "AI in the IDE, governed",
    oneLiner: "One policy across every AI tool your engineers actually use.",
    persona: "Security engineers, platform leads, CISO teams standardizing developer AI.",
    situation:
      "Your engineers use Claude Code, Cursor, Copilot, Windsurf, Codex, ChatGPT desktop, and Claude desktop. Each one speaks to a different model, over a different API, using a different tool surface. Your policy is a wiki page. Most of the time, nobody has read it.",
    mechanics: [
      "Two integration paths. A hook inside the tool where the tool supports it (Claude Code hooks, Copilot CLI, Cursor). A transparent proxy on the model endpoint where it does not. Same policy engine on both.",
      "Every call returns allow, warn, or block before it proceeds. Fail closed. Hash-chained audit for every decision.",
      "Rules live as declarative YAML. Security ships a rule change without a deploy.",
    ],
    scenario:
      "A developer pastes a customer email into Cursor to draft a reply endpoint. The email contains a raw credit card number. Guard sees the prompt, matches the PAN pattern, blocks the call, and shows the rule that fired. The developer strips the number and retries. Nothing left the machine.",
    metrics:
      "Policy violations blocked per day. Unique models in use. Per-tool cost. Coverage: what fraction of your AI calls actually go through Guard.",
    integrations:
      "Anthropic, OpenAI, Azure OpenAI, Google, Perplexity, OpenRouter, Vercel AI Gateway. Any provider your engineers route through.",
    ctaLabel: "Install Guard hook",
    ctaHref: "/docs#cli-install",
  },
  {
    n: "02",
    slug: "mcp-governance",
    title: "MCP that behaves like a permitted action, not a shell",
    oneLiner: "Every MCP call becomes a governed call.",
    persona: "AI platform teams shipping or consuming MCP servers.",
    situation:
      "MCP made every tool a callable. That was the point. It also made every tool an unguarded shell if the model on the other end decides to call it. Most teams have no throttle, no per-tool allowlist, and no audit of which agent invoked which tool at which time.",
    mechanics: [
      "Guard proxies MCP calls. Per-tool rate caps. Per-server allowlists. Per-agent scope. All decisions land in the same hash-chained audit as your model calls.",
      "Tools that write, delete, or send can require review. Tools that read stay fast.",
      "A single /guard/mcp endpoint per workspace. One place to point every client.",
    ],
    scenario:
      "An analytics agent has access to an MCP tool that runs SQL on the warehouse. A user asks it to export a customer table to CSV. Guard sees the row estimate, the destination, and the PII columns in the projection. It blocks with a specific rule cited. The analyst sees the block reason without needing to open the warehouse logs.",
    metrics:
      "MCP calls per tool. Blocked calls by rule. Median latency Guard adds to a tool call. Per-agent tool usage.",
    integrations:
      "Any MCP server, self-hosted or third-party. Vercel MCP, Cloudflare MCP, custom servers.",
    ctaLabel: "Wire Guard MCP",
    ctaHref: "/docs#cli-mcp",
  },
  {
    n: "03",
    slug: "security-loop",
    title: "Scan to fix, closed",
    oneLiner: "The loop is the deliverable, not the report.",
    persona: "Application security, security engineering, GRC.",
    situation:
      "A scanner produces a finding. The finding lands in a Jira ticket. The ticket ages. Six weeks later it is fixed by a stressed engineer, silently downgraded, or lost. The scanner report was the deliverable. The fix was somebody else’s problem.",
    mechanics: [
      "Findings from scanners feed one table. Above a configurable threshold, an autopilot playbook drafts the mitigation PR.",
      "A human reviews and approves. The approval, the PR, the CI check, and the merged commit sign into one hash-chained record.",
      "Scan-to-fix distance becomes a number you can graph and move.",
    ],
    scenario:
      "Semgrep flags a hardcoded API key in a repo. The autopilot playbook opens a PR that moves the key to the secret manager, updates the reference, and adds a test that no known key patterns are present in the diff. The code owner approves. The PR merges. The finding closes with the merge SHA and the reviewer identity attached to the audit chain.",
    metrics:
      "Mean time to remediation. Findings closed per week. Autopilot success rate. Human approvals per week.",
    integrations:
      "Semgrep, Trivy, Snyk, Gitleaks, GitHub Advanced Security. Any scanner that produces SARIF or JSON.",
    ctaLabel: "Install Security Loop",
    ctaHref: "/solutions/security-loop",
  },
  {
    n: "04",
    slug: "compliance-evidence",
    title: "Compliance evidence from what the AI actually did",
    oneLiner: "One hash-chained table, mapped to every framework you care about.",
    persona: "Compliance officers, GRC leads, auditors in regulated environments.",
    situation:
      "Auditors have started asking about AI usage. Most companies answer with screenshots, a vendor letter, or the SOC 2 report the model provider gave them. That is evidence the vendor has controls. It is not evidence that you do.",
    mechanics: [
      "Every allow, warn, block, finding, fix, and approval is a signed row.",
      "Compliance packs map that table to specific controls. SOC 2 CC7.3 and PCI DSS 12.3.1 point at the same rows. ISO 27001 A.14.2.1 and the EU AI Act share the map.",
      "When an auditor asks how you enforce your AI usage policy, the answer is a query, not a slide.",
    ],
    scenario:
      "SOC 2 Type II auditor asks how you prevent hardcoded secrets from being generated by AI tools. You show the Guard rule that fires on secret patterns, the audit chain of the last 90 days of allow and block decisions on that rule, and the tickets opened for engineers whose calls were blocked. The auditor moves on.",
    metrics: "Framework control coverage. Evidence rows per control. Days until audit ready.",
    integrations:
      "SOC 2, PCI DSS, HIPAA, ISO 27001, EU AI Act, NIST AI RMF. Custom pack for internal frameworks.",
    ctaLabel: "Browse compliance packs",
    ctaHref: "/registry?tab=compliance",
  },
  {
    n: "05",
    slug: "spend-guardrails",
    title: "Cost guardrails that stop the call",
    oneLiner: "Limits enforced at the proxy, not discovered on the invoice.",
    persona: "FinOps, engineering leadership, anyone who has been surprised by an AI invoice.",
    situation:
      "One agent misconfigured on a Friday can burn a month of your model budget over a weekend. Provider dashboards show the damage after the fact. Finance hears about it on Monday. The engineer who wrote the loop hears about it on Tuesday.",
    mechanics: [
      "Per-user daily caps. Per-project monthly caps. Per-agent lifetime caps. All enforced at the proxy, at the moment of the call.",
      "Warn thresholds page the owner before the block threshold hits.",
      "When a cap is reached, the call fails cleanly with a rule that names the limit and the owner.",
    ],
    scenario:
      "A nightly PR reviewer agent hits a retry loop after a schema change. Its cost climbs at 200x the normal rate. At the per-agent daily warn threshold, Slack pings the owning team. At the block threshold, Guard stops the calls. The morning after, the agent report shows the cap enforced, not the runaway.",
    metrics: "Cost under policy. Warn events. Block events. Utilization by owner.",
    integrations: "Anthropic, OpenAI, Azure OpenAI, Bedrock, any provider Guard proxies.",
    ctaLabel: "Set a cap",
    ctaHref: "/theguard/spend",
  },
  {
    n: "06",
    slug: "shadow-ai-discovery",
    title: "Shadow AI, found",
    oneLiner: "Discovery first. Then policy. Then evidence.",
    persona: "Security, IT, CISO teams doing an AI inventory before writing rules.",
    situation:
      "You cannot govern what you did not know was running. Engineers connect Cursor to a personal Anthropic account. Someone installs an MCP server from a GitHub gist. A support agent pastes a customer sample into a chat window. Your policy is silent on tools it has not heard of.",
    mechanics: [
      "A lightweight watch daemon reports which AI CLIs and desktop apps are running on developer machines.",
      "Self-registration lets any tool that connects to the Guard proxy declare itself.",
      "MCP servers announce their tool surface at registration.",
    ],
    scenario:
      "A security lead runs discovery for the first time. The report shows 47 developers on Cursor, 12 on Windsurf that were not on any approved list, three running local Ollama servers, and one MCP server pointed at a production Postgres from a home lab. The policy conversation starts from a list, not a guess.",
    metrics: "Unique tools discovered. Unique models discovered. MCP servers registered. Users with unmanaged AI usage.",
    integrations: "Claude Code, Cursor, Copilot, Windsurf, ChatGPT desktop, Claude desktop, Codex, custom CLIs.",
    ctaLabel: "Run discovery",
    ctaHref: "/theguard/discovery",
  },
  {
    n: "07",
    slug: "agent-identity",
    title: "Agents get an identity, not a shared API key",
    oneLiner: "Every run is a bounded session. Every credential expires with the run.",
    persona: "Platform engineering teams standing up agent fleets.",
    situation:
      "An agent is not a user. It is not a service account either. Most orgs give the agent a static API key, tape it into a secrets manager, and hope it does not leak. When the agent misbehaves, revocation is manual, credential rotation is a ticket, and there is no clean way to prove which specific run made which specific call.",
    mechanics: [
      "The executor mints two tokens at run start. cond_run for proxy authorization. cond_cred for credential brokerage.",
      "Both are scoped to the run, expire when the run ends, and revoke instantly on policy violation.",
      "The executor is the only minter. No fallback path. No user-token reuse. No trigger-time shortcut.",
      "Agent role permits describe what any run in that role can do. Rotation is a config change.",
    ],
    scenario:
      "A code-review agent starts. Guard issues a cond_run scoped to the model calls the playbook needs, and a cond_cred scoped to the GitHub PR API for that repo only. The run finishes. Both tokens die. If the run had tried to call the payroll API instead, cond_cred would have refused before GitHub was ever contacted.",
    metrics: "Active identities. Median session length. Revocations per week. Unused credential scopes.",
    integrations: "Okta, Azure AD, Google Workspace as identity source. Guard is the runtime authority.",
    ctaLabel: "Provision an agent identity",
    ctaHref: "/agent-identity",
  },
  {
    n: "08",
    slug: "content-inspection",
    title: "Prompt injection and PII, caught at the wire",
    oneLiner: "Inspect content before the model sees it.",
    persona: "Security teams handling untrusted documents, customer content, or web-scraped input.",
    situation:
      "Prompt injection is not a bug you patch in a model version. A model that reads instructions from content will follow instructions from content. Redacting PII after the model has read it is also too late. Both have to be handled before the model gets the payload.",
    mechanics: [
      "Guard inspects prompt content at the proxy. Injection patterns trigger a rule that either blocks or strips the offending region.",
      "PII patterns trigger redaction. The model sees a placeholder instead of the raw value.",
      "Custom rules handle domain-specific terms. YAML, not code. Ship without a deploy.",
    ],
    scenario:
      "A support agent summarizes a customer email. The email contains injected text asking the model to forward the entire thread to an external address. Guard’s injection rule fires, strips the region, and marks the call warn. The summary runs on the sanitized content. A note lands in the run’s audit trail. The support engineer sees a clean summary and a small sanitized banner.",
    metrics: "Injections blocked. PII redactions. False-positive rate on custom rules.",
    integrations: "Any prompt, any model, any tool that routes through the Guard proxy.",
    ctaLabel: "Enable content inspection",
    ctaHref: "/theguard/policies",
    note: "The rule library covers common patterns. Domain-specific rules are shipping on a rolling basis.",
  },
  {
    n: "09",
    slug: "action-governance",
    title: "Business agents that take real actions",
    oneLiner: "What your agent does. Not just what it can.",
    persona: "Heads of CX, ops leaders, and CISOs deploying customer-facing or ops-facing AI agents.",
    situation:
      "An agent that answers questions is a search box with a hallucination risk. An agent that issues refunds, cancels subscriptions, updates accounts, or commits pricing is a financial actor with the same risk. Air Canada honored the bereavement fare its chatbot invented. Klarna reversed thousands of automated CX actions when a rules change misfired. The failure is not that the agent could talk. The failure is that the agent could act without a policy in front of the action.",
    mechanics: [
      "Guard sits between the agent and the action tool. Every action call is checked against the current policy: is this refund inside the allowed amount, is this cancellation inside the allowed reason list, does this commitment need a supervisor.",
      "Warn triggers a human handoff. Block returns a clean refusal the agent can explain in language.",
      "Every action becomes one hash-chained line with the customer, the amount, the reason, and the reviewer.",
    ],
    scenario:
      "A support agent offers a $400 credit to a customer whose bill was $180. Guard sees the tool call before the credit hits billing, checks the per-transaction cap for the agent’s role, and returns block with the rule cited: credit cannot exceed twice the disputed amount. The agent tells the customer it needs a supervisor. The supervisor approves. The credit posts. Finance sees the audit line, not the mistake.",
    metrics: "Actions above threshold. Human handoffs per week. Out-of-policy attempts. Median handoff time.",
    integrations: "Any agent framework (Sierra, LangChain, custom). Any action API (Stripe, Zendesk, Salesforce, internal tools).",
    ctaLabel: "Gate an action tool",
    ctaHref: "/solutions/action-governance",
  },
]

export default function UseCasesPage() {
  return (
    <>
      <Hero />
      <Summary />
      {CASES.map((c) => (
        <Detail key={c.slug} c={c} />
      ))}
      <BottomCta />
    </>
  )
}

function Hero() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-14 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        Nine surfaces we operate in today
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        Where Guard already runs, in production.
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-4">
        Nine use cases. Every one is a shipped surface. Where a surface is partial, we say so on the card.
        Where a link goes straight to the app, it will route anonymous visitors through sign-in and drop them
        back where they were headed.
      </p>
      <p className="text-base text-stone-500 max-w-2xl mx-auto leading-relaxed italic mb-4">
        Your identity provider tells you who your agents are. Guard governs what they do.
      </p>
      <p className="text-base text-stone-500 max-w-2xl mx-auto leading-relaxed italic">
        Governance is not a brake. It is the scaffolding that lets you expand agent autonomy safely.
      </p>
    </section>
  )
}

function Summary() {
  return (
    <section className="max-w-6xl mx-auto px-6 pb-16">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {CASES.map((c) => (
          <a
            key={c.slug}
            href={`#${c.slug}`}
            className="block rounded-2xl border border-stone-200 bg-white p-5 hover:border-stone-400 transition-colors"
          >
            <div className="flex items-center gap-3 mb-3">
              <span className="text-xs font-mono text-stone-400">{c.n}</span>
              <span className="text-xs uppercase tracking-widest text-stone-500">Use case</span>
            </div>
            <div className="text-lg font-bold text-stone-900 mb-2 leading-snug">{c.title}</div>
            <div className="text-sm text-stone-500 leading-relaxed">{c.oneLiner}</div>
          </a>
        ))}
      </div>
    </section>
  )
}

function Detail({ c }: { c: UseCase }) {
  return (
    <section id={c.slug} className="max-w-3xl mx-auto px-6 py-16 border-t border-stone-100">
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xs font-mono text-stone-400">{c.n}</span>
        <span className="text-xs uppercase tracking-widest text-indigo-700 font-semibold">{c.persona}</span>
      </div>
      <h2 className="text-3xl sm:text-4xl font-black tracking-tight text-stone-900 leading-tight mb-4">
        {c.title}
      </h2>
      <p className="text-lg text-stone-500 leading-relaxed mb-8">{c.oneLiner}</p>

      <h3 className="text-sm font-semibold uppercase tracking-widest text-stone-500 mb-3">The situation</h3>
      <p className="text-stone-700 leading-relaxed mb-8">{c.situation}</p>

      <h3 className="text-sm font-semibold uppercase tracking-widest text-stone-500 mb-3">What Guard does</h3>
      <ul className="space-y-3 mb-8">
        {c.mechanics.map((m, i) => (
          <li key={i} className="flex gap-3 text-stone-700 leading-relaxed">
            <span className="text-indigo-500 flex-shrink-0">âº</span>
            <span>{m}</span>
          </li>
        ))}
      </ul>

      <h3 className="text-sm font-semibold uppercase tracking-widest text-stone-500 mb-3">A concrete run</h3>
      <p className="text-stone-700 leading-relaxed mb-8">{c.scenario}</p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-widest text-stone-500 mb-2">Metrics that move</h3>
          <p className="text-stone-700 text-sm leading-relaxed">{c.metrics}</p>
        </div>
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-widest text-stone-500 mb-2">Where it plugs in</h3>
          <p className="text-stone-700 text-sm leading-relaxed">{c.integrations}</p>
        </div>
      </div>

      {c.note && (
        <p className="text-xs text-stone-500 italic mb-6 border-l-2 border-stone-200 pl-3">{c.note}</p>
      )}

      <div className="flex flex-wrap items-center gap-4 pt-2">
        <a
          href={c.ctaHref}
          className="rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
        >
          {c.ctaLabel}
        </a>
        <a
          href="#top"
          className="text-sm text-stone-500 hover:text-stone-900 transition-colors"
        >
          Back to top
        </a>
      </div>
    </section>
  )
}

function BottomCta() {
  return (
    <section className="max-w-3xl mx-auto px-6 py-20 text-center border-t border-stone-100">
      <h2 className="text-3xl sm:text-4xl font-black tracking-tight text-stone-900 leading-tight mb-4">
        Not sure which one is you?
      </h2>
      <p className="text-lg text-stone-500 leading-relaxed mb-8">
        Most teams land in three at once. Pick the one that hurts the most today.
        The other two will be on the same Guard install.
      </p>
      <CtaLink className="rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors" />
    </section>
  )
}
