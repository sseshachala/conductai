import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "MCP Gateway — One phone book for every AI agent's tools | Conduct",
  description:
    "Your agents ask Guard which MCP servers they can reach, get short-lived scoped tokens, and every tool call is policy-checked and hash-chained. Stop hardcoding endpoints. Rotate once, revoke instantly, audit everything.",
}

export default function MCPGatewayPage() {
  return (
    <>
      <HeroSection />
      <PositioningStrip />
      <FeatureGrid />
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
      icon: "🔌",
      title: "Boot-time discovery",
      body: "guard.discover_mcps() returns the tools this agent may reach right now, with time-bounded scoped tokens.",
    },
    {
      icon: "🔑",
      title: "Per-agent credential brokering",
      body: "Rotate a GitHub app token once. Every agent picks it up on next boot. Zero redeploys.",
    },
    {
      icon: "🎯",
      title: "Policy per tool intent",
      body: "\u201cThis agent may call GitHub MCP, but only for read operations.\u201d Two lines of YAML. Blocked calls log the rule id.",
    },
    {
      icon: "🔗",
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
          Every enterprise with more than three AI agents has the same problem. Each agent hardcodes its own copy of every tool endpoint and every credential. Rotate a token, redeploy 20 things. Guard becomes the one place agents ask &ldquo;what tools am I allowed to reach right now, and with what credentials?&rdquo; and every tool call goes through a policy check with hash-chained audit. LiteLLM solved model sprawl. Nobody solved tool sprawl. That is Guard.
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
