import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "We built the missing MCP Gateway — LiteLLM solved model sprawl, nobody solved tool sprawl | Conduct",
  description:
    "Guard now speaks a boot-time API. Agents call guard.discover_mcps() and get a policy-filtered list of MCP servers with per-agent scoped tokens. No hardcoded endpoints, no long-lived credentials, every tool call hash-chained.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Launch
          </span>
          <span className="text-xs text-stone-400">Coming soon</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          We built the missing MCP Gateway.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          LiteLLM solved model sprawl. Nobody solved tool sprawl. So we did.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">
        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          The problem nobody named
        </h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          If you run three or more AI agents, they each have a copy of every MCP endpoint and every credential pasted into their config or env vars. GitHub MCP token here, Slack MCP token there, Confluence MCP token in a third place. Rotate one credential, redeploy 20 things. Revoke access, edit 20 files. Ask your CISO &ldquo;did any agent hit customer data last night?&rdquo; and start grepping across 20 log formats.
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          The LLM proxy category (LiteLLM, Portkey, OpenRouter, Vercel AI Gateway) solved a real thing. Model call sprawl. One endpoint, hundreds of providers, unified auth, cost tracking. Great work. Not this problem. Those proxies live at the model layer. Tool sprawl is a floor down, at the MCP layer.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          What we shipped
        </h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Guard now speaks a boot-time API. Agents start with one call:
        </p>

        <pre className="bg-stone-900 text-stone-100 rounded-lg px-4 py-3 text-sm overflow-x-auto mb-4">
          <code>{`mcps = guard.discover_mcps()`}</code>
        </pre>

        <p className="text-stone-700 leading-relaxed mb-4">
          Guard returns a policy-filtered list of MCP servers the agent may reach, along with a short-lived scoped token per server. The agent never sees a long-lived credential. It never hardcodes an endpoint. Its config is empty of MCP details.
        </p>

        <p className="text-stone-700 leading-relaxed mb-2">Behind that call:</p>
        <ul className="text-stone-700 leading-relaxed mb-6 space-y-2 list-disc pl-6">
          <li>
            <strong>A workspace catalog</strong> of MCP servers, maintained centrally.
          </li>
          <li>
            <strong>Per-agent scoped tokens</strong> minted on demand, TTL-bounded, revocable per agent.
          </li>
          <li>
            <strong>Policy packs</strong> with two new keys, <code>mcp_scope</code> and <code>mcp_actions</code>, so &ldquo;this agent may call GitHub MCP but only for read operations&rdquo; is one line of YAML.
          </li>
          <li>
            <strong>Hash-chained audit</strong> on every tool call, with the resolving policy rule id attached. Exportable to SIEM.
          </li>
          <li>
            <strong>Auto-discovery</strong> that watches your existing agent configs (<code>.mcp.json</code>, Claude Desktop, Cursor, Windsurf) and promotes newly-found MCP servers into the catalog in observation mode.
          </li>
        </ul>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          What this looks like for a platform team
        </h2>
        <p className="text-stone-700 leading-relaxed mb-3">
          Rotate the GitHub app token: one action in Guard, zero agent redeploys. Every agent picks up the new token on next <code>discover_mcps()</code> call.
        </p>
        <p className="text-stone-700 leading-relaxed mb-3">
          Revoke the finance agent&rsquo;s source-control access: one policy rule, effective on the next agent tick.
        </p>
        <p className="text-stone-700 leading-relaxed mb-3">
          Add a new MCP server: admin approves in Guard, every agent sees it on next boot if policy allows.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          CISO asks &ldquo;did any agent touch customer-data MCP last night?&rdquo;: one query against the hash-chained log.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          Why nobody has shipped this yet
        </h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          MCP is a young standard. The vendors with existing distribution (LLM proxies) point at model calls, not tool calls. The tool side has a lot of MCP <em>servers</em> now, and a growing set of MCP <em>clients</em> (Claude Desktop, Cursor, Copilot, Cline), but no one has occupied the gateway spot between them. That is what Guard is now.
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          The moat is not the four bullets above. Each of them is a page of code. The moat is that we already had the hash-chain audit, the token vault, the policy engine, the discovery daemon, and the pack schema. This launch is a bridge across primitives we shipped over the last 18 months, exposed through one new front door.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Try it</h2>

        <pre className="bg-stone-900 text-stone-100 rounded-lg px-4 py-3 text-sm overflow-x-auto mb-6">
          <code>{`pip install conduct-cli
conduct login
conduct mcp list             # see the workspace catalog
conduct mcp rotate github    # rotate a credential`}</code>
        </pre>

        <p className="text-stone-700 leading-relaxed mb-8">
          Docs:{" "}
          <a href="/mcp-gateway" className="text-indigo-600 hover:underline">
            conductai.ai/mcp-gateway
          </a>
          <br />
          Source:{" "}
          <a
            href="https://github.com/sseshachala/conductai/issues/1246"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 hover:underline"
          >
            github.com/sseshachala/conductai (issue #1246)
          </a>
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          One line for your slide deck
        </h2>
        <blockquote className="border-l-4 border-indigo-500 pl-6 py-2 text-stone-700 italic mb-8">
          LiteLLM makes model calls fungible. Guard makes tool access governable. We are not a competing proxy. We are the layer no proxy touches.
        </blockquote>

        <div className="not-prose flex flex-wrap gap-3 mt-12 mb-8">
          <a
            href="/mcp-gateway"
            className="inline-flex items-center gap-2 rounded-lg bg-stone-900 text-white px-5 py-3 text-sm font-semibold hover:bg-stone-800 transition-colors"
          >
            MCP Gateway landing
          </a>
          <a
            href="https://github.com/sseshachala/conductai/issues/1246"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white text-stone-700 px-5 py-3 text-sm font-semibold hover:border-stone-300 hover:shadow-sm transition-all"
          >
            View epic on GitHub
          </a>
        </div>

        <div className="mt-16 pt-8 border-t border-stone-200">
          <CtaLink className="inline-flex items-center gap-2 rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors" />
        </div>
      </div>
    </article>
  )
}
