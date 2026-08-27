import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "MCP Gateway — One phone book for every AI agent's tools | Conduct",
  description:
    "Your agents ask Guard which MCP servers they can reach, get short-lived scoped tokens, and every tool call is policy-checked and hash-chained. Pre-canned Registry + Bring Your Own MCP. Per-tool policy enforcement.",
}

export default function MCPGatewayPage() {
  return (
    <>
      <HeroSection />
      <PositioningStrip />
      <FeatureGrid />
      <RegistrySection />
      <UseCasesSection />
      <ComparisonSection />
      <ElevatorSection />
      <CtaFooterSection />
    </>
  )
}

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-12 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 border border-indigo-100 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-4">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        Early access
      </div>
      <div className="inline-flex items-center gap-2 bg-stone-100 text-stone-600 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8 ml-2">
        <span className="w-1.5 h-1.5 rounded-full bg-stone-400 inline-block" />
        MCP Gateway
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-5">
        One phone book for every AI agent&rsquo;s tools.
      </h1>
      <p className="text-xl text-stone-500 max-w-3xl mx-auto leading-relaxed mb-10">
        Your agents ask Guard which MCP servers they can reach, get short-lived scoped tokens, and every tool call is policy-checked and hash-chained. Stop hardcoding endpoints. Stop pasting credentials into 20 configs. Rotate once, revoke instantly, audit everything.
      </p>
      <div className="flex flex-wrap justify-center gap-3">
        <a
          href="mailto:hello@conductai.ai?subject=MCP%20Gateway%20early%20access"
          className="inline-flex items-center gap-2 rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
        >
          Get early access
        </a>
        <a
          href="https://github.com/sseshachala/conductai/issues/1246"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          See the epic
        </a>
      </div>
    </section>
  )
}

function PositioningStrip() {
  return (
    <section className="max-w-5xl mx-auto px-6 pb-12">
      <div className="bg-stone-900 text-white rounded-2xl px-8 py-8 text-center">
        <p className="text-xl sm:text-2xl font-semibold leading-relaxed">
          LiteLLM makes model calls fungible.
          <br />
          Guard makes tool access governable.
        </p>
        <p className="text-sm text-stone-400 mt-3 font-medium">
          Different phone, different problem, different room.
        </p>
      </div>
    </section>
  )
}

function FeatureGrid() {
  const features: { icon: string; title: string; body: string }[] = [
    {
      icon: "\ud83d\udd0c",
      title: "Boot-time discovery",
      body: "guard.discover_mcps() returns the tools this agent may reach right now, with time-bounded scoped tokens.",
    },
    {
      icon: "\ud83d\udd11",
      title: "Per-agent credential brokering",
      body: "Rotate a GitHub app token once. Every agent picks it up on next boot. Zero redeploys.",
    },
    {
      icon: "\ud83c\udfaf",
      title: "Policy per tool intent",
      body: "\u201cThis agent may call GitHub MCP, but only for read operations.\u201d Two lines of YAML. Blocked calls log the rule id.",
    },
    {
      icon: "\ud83d\udd17",
      title: "Hash-chained audit",
      body: "Every tool call is tamper-evident. Export to SIEM. Answer \u201cdid any agent touch customer-data last night\u201d in one query.",
    },
  ]
  return (
    <section className="max-w-5xl mx-auto px-6 pb-16">
      <div className="grid sm:grid-cols-2 gap-6">
        {features.map(f => (
          <div key={f.title} className="border border-stone-200 rounded-xl bg-white p-6">
            <div className="text-2xl mb-3">{f.icon}</div>
            <h3 className="text-lg font-bold text-stone-900 mb-2">{f.title}</h3>
            <p className="text-sm text-stone-600 leading-relaxed">{f.body}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

function RegistrySection() {
  const canned: { name: string; icon: string }[] = [
    { name: "GitHub", icon: "\ud83d\udc19" },
    { name: "Slack", icon: "\ud83d\udcac" },
    { name: "Postgres", icon: "\ud83d\udc18" },
    { name: "Filesystem", icon: "\ud83d\udcc1" },
    { name: "Confluence", icon: "\ud83d\udcd8" },
    { name: "Jira", icon: "\ud83d\udccb" },
    { name: "GDrive", icon: "\ud83d\udcc2" },
    { name: "Sentry", icon: "\ud83d\udea8" },
    { name: "Linear", icon: "\ud83d\udcd0" },
    { name: "Notion", icon: "\ud83d\udcdd" },
  ]
  const perToolRows: { icon: string; iconColor: string; tool: string; verdict: string }[] = [
    { icon: "\u2713", iconColor: "text-emerald-600", tool: "GitHub.create_issue", verdict: "Allowed" },
    { icon: "\u26a0", iconColor: "text-yellow-600", tool: "GitHub.merge_pr", verdict: "Requires human approval" },
    { icon: "\u2715", iconColor: "text-red-600", tool: "Postgres.execute", verdict: "Blocked" },
    { icon: "\u2713", iconColor: "text-emerald-600", tool: "Postgres.query", verdict: "Allowed (read-only)" },
  ]
  return (
    <section className="max-w-5xl mx-auto px-6 pb-16">
      <div className="text-center mb-10">
        <h2 className="text-3xl font-black tracking-tight text-stone-900 mb-2">
          Registry + Bring Your Own
        </h2>
        <p className="text-stone-500 max-w-2xl mx-auto">
          Two catalog sources, one enforcement layer. Every tool call is policy-checked whether the MCP shipped with Guard or you registered it yourself.
        </p>
      </div>
      <div className="grid md:grid-cols-2 gap-6">
        <div className="border border-stone-200 rounded-xl bg-white p-6">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold uppercase tracking-widest text-indigo-700 bg-indigo-50 border border-indigo-100 px-2.5 py-1 rounded-full">
              Pre-canned
            </span>
            <h3 className="text-lg font-bold text-stone-900">Conduct Registry</h3>
          </div>
          <p className="text-sm text-stone-600 leading-relaxed mb-4">
            Curated MCPs with default policy packs already attached per tool. Click Enable, get sensible defaults (approval on writes, read-only for restricted roles, PII redaction on outputs). No week of policy writing before day one.
          </p>
          <div className="grid grid-cols-5 gap-2">
            {canned.map(m => (
              <div key={m.name} className="flex flex-col items-center gap-1 p-2 rounded-lg bg-stone-50 border border-stone-100">
                <span className="text-xl">{m.icon}</span>
                <span className="text-[10px] font-semibold text-stone-500">{m.name}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-stone-400 mt-3">10 MCPs at launch, more each month.</p>
        </div>
        <div className="border border-stone-200 rounded-xl bg-white p-6">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold uppercase tracking-widest text-stone-700 bg-stone-100 border border-stone-200 px-2.5 py-1 rounded-full">
              Bring your own
            </span>
            <h3 className="text-lg font-bold text-stone-900">Private MCPs</h3>
          </div>
          <p className="text-sm text-stone-600 leading-relaxed mb-4">
            Register any MCP server. Guard introspects it via the standard tools/list call, pulls every tool schema, and lets admins attach policy packs per tool.
          </p>
          <pre className="bg-stone-900 text-stone-100 rounded-lg px-3 py-2 text-xs overflow-x-auto">
            <code>{`$ conduct mcp add https://internal.mcp/finance
  \u2192 17 tools introspected
  \u2192 default pack applied (read-only)
  \u2192 admin approval required to enable writes`}</code>
          </pre>
          <p className="text-xs text-stone-400 mt-3">Per-tool policies, not per-server.</p>
        </div>
      </div>

      <div className="mt-6 border border-stone-200 rounded-xl bg-stone-50 p-6">
        <p className="text-xs font-bold uppercase tracking-widest text-stone-500 mb-3">
          Per-tool policy examples
        </p>
        <div className="grid sm:grid-cols-2 gap-3 text-sm">
          {perToolRows.map(r => (
            <div key={r.tool} className="flex items-start gap-3 bg-white border border-stone-200 rounded-lg p-3">
              <span className={`${r.iconColor} font-bold mt-0.5`}>{r.icon}</span>
              <div>
                <p className="font-semibold text-stone-800">{r.tool}</p>
                <p className="text-xs text-stone-500">{r.verdict}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function UseCasesSection() {
  const cases: { persona: string; title: string; before: string; after: string }[] = [
    {
      persona: "Platform Ops",
      title: "End MCP tool sprawl",
      before:
        "Every agent has a copy of every MCP endpoint and every credential pasted into its config. Onboarding a new MCP means 20 config edits and 20 redeploys.",
      after:
        "One central catalog. Agents ask guard.discover_mcps() at boot. New MCPs propagate to every agent on next boot, no code changes.",
    },
    {
      persona: "Security",
      title: "Least privilege per agent",
      before:
        "Every agent shares one long-lived MCP token with full workspace scope. Blast radius of a compromised agent is every tool that token can touch.",
      after:
        "Per-agent scoped tokens minted on demand, TTL-bounded, revocable per agent. \u201cThis agent may call GitHub MCP only for read.\u201d Two lines of YAML.",
    },
    {
      persona: "Compliance & Audit",
      title: "Prove every tool call",
      before:
        "\u201cDid any agent hit customer-data MCP last night?\u201d = grep across 20 log formats, hope you have retention, hope nothing was rotated out.",
      after:
        "One query against the hash-chained audit log. Tamper-evident, resolving policy rule id attached to every call. SIEM-exportable.",
    },
    {
      persona: "AI Coding Assistants",
      title: "Govern Cursor, Copilot, Claude Desktop, Cline",
      before:
        "Developers install MCP servers ad hoc into their IDE configs. Central IT has zero visibility into which tools their AI assistants can reach.",
      after:
        "Discovery daemon detects MCPs registered in .mcp.json, Claude Desktop, Cursor, Windsurf. Central catalog with observe-then-enforce toggle. Devs use approved MCPs, everything else logged.",
    },
    {
      persona: "AI Product Team",
      title: "Ship agents in a week, not a quarter",
      before:
        "Enabling GitHub + Slack + Postgres MCPs for an agent means a week of reading MCP docs, writing per-tool rules, testing, and hoping nothing was missed.",
      after:
        "Enable pre-canned MCPs from the Conduct Registry. Sensible default policies attached per tool. Tune later. Ship this week.",
    },
  ]
  return (
    <section className="max-w-5xl mx-auto px-6 pb-16">
      <div className="text-center mb-10">
        <h2 className="text-3xl font-black tracking-tight text-stone-900 mb-2">
          Use cases
        </h2>
        <p className="text-stone-500">
          Where MCP Gateway earns its place in the stack.
        </p>
      </div>
      <div className="grid sm:grid-cols-2 gap-6">
        {cases.map(c => (
          <div
            key={c.title}
            className="border border-stone-200 rounded-xl bg-white p-6 flex flex-col"
          >
            <p className="text-[10px] font-bold uppercase tracking-widest text-indigo-700 mb-2">
              {c.persona}
            </p>
            <h3 className="text-lg font-bold text-stone-900 mb-4">{c.title}</h3>
            <div className="mb-4">
              <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-1">
                Before
              </p>
              <p className="text-sm text-stone-600 leading-relaxed">{c.before}</p>
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-indigo-700 mb-1">
                With MCP Gateway
              </p>
              <p className="text-sm text-stone-700 leading-relaxed">{c.after}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function ComparisonSection() {
  const rows: [string, string, string][] = [
    ["Governs", "Model calls", "Tool calls"],
    ["Audit granularity", "Completion", "Tool invocation"],
    ["Credential type", "Inbound provider keys", "Outbound tool credentials"],
    ["Policy vocabulary", "Model requests", "Tool intent"],
    ["Answers \u201cwho called what\u201d", "Model, prompt", "Tool, arguments, side effect"],
    ["Category age", "Mature", "Empty (nobody has planted the flag)"],
  ]
  return (
    <section className="max-w-5xl mx-auto px-6 pb-16">
      <div className="text-center mb-8">
        <h2 className="text-3xl font-black tracking-tight text-stone-900 mb-2">
          Not a competing proxy.
        </h2>
        <p className="text-stone-500">A different layer entirely.</p>
      </div>
      <div className="overflow-x-auto border border-stone-200 rounded-xl bg-white">
        <table className="w-full text-sm">
          <thead className="bg-stone-50 border-b border-stone-200">
            <tr>
              <th className="text-left px-6 py-3 text-xs font-bold uppercase tracking-widest text-stone-500"></th>
              <th className="text-left px-6 py-3 text-xs font-bold uppercase tracking-widest text-stone-500">
                LLM Proxy (LiteLLM, Portkey)
              </th>
              <th className="text-left px-6 py-3 text-xs font-bold uppercase tracking-widest text-indigo-700">
                MCP Gateway (Guard)
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, a, b]) => (
              <tr key={label} className="border-b border-stone-100 last:border-b-0">
                <td className="px-6 py-4 font-semibold text-stone-700">{label}</td>
                <td className="px-6 py-4 text-stone-600">{a}</td>
                <td className="px-6 py-4 text-indigo-700 font-medium">{b}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function ElevatorSection() {
  return (
    <section className="max-w-3xl mx-auto px-6 pb-16">
      <div className="border-l-4 border-indigo-500 bg-indigo-50/50 rounded-r-xl px-8 py-6">
        <p className="text-lg text-stone-700 leading-relaxed">
          Every enterprise with more than three AI agents has the same problem. Each agent hardcodes its own copy of every tool endpoint and every credential. Rotate a token, redeploy 20 things. Guard becomes the one place agents ask &ldquo;what tools am I allowed to reach right now, and with what credentials?&rdquo; Enable pre-canned MCPs from the Registry with sensible defaults, or register your own private MCPs and Guard introspects the tool schemas so you attach policy per tool. Every call is hash-chained. LiteLLM solved model sprawl. Nobody solved tool sprawl. That is Guard.
        </p>
      </div>
    </section>
  )
}

function CtaFooterSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pb-24">
      <div className="border border-stone-200 rounded-2xl bg-white p-10 text-center">
        <h2 className="text-3xl font-black tracking-tight text-stone-900 mb-3">
          Ready to stop pasting MCP tokens into 20 configs?
        </h2>
        <p className="text-stone-500 max-w-xl mx-auto mb-8">
          MCP Gateway is in early access. Get on the list to try the boot-time discovery API and per-agent credential brokering the day it opens.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <a
            href="mailto:hello@conductai.ai?subject=MCP%20Gateway%20early%20access"
            className="inline-flex items-center gap-2 rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
          >
            Get early access
          </a>
          <a
            href="https://github.com/sseshachala/conductai/issues/1246"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
          >
            Read the build epic
          </a>
          <CtaLink className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all" />
        </div>
      </div>
    </section>
  )
}
