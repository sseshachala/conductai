import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "One policy in front of 400+ models — Guard on OpenRouter | Conduct",
  description:
    "Point Conduct Guard at OpenRouter and every model you route through it — Claude, GPT, Gemini, Llama, Mistral, DeepSeek — enforces the same policy before the request leaves your network.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-orange-700 bg-orange-50 border border-orange-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Integrations
          </span>
          <span className="text-xs text-stone-400">August 24, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          One policy in front of 400+ models.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          Point Conduct Guard at OpenRouter and every model you route
          through it — Claude, GPT, Gemini, Llama, Mistral, DeepSeek —
          enforces the same policy before the request leaves your
          network.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">
        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Why OpenRouter</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          OpenRouter gives you one API and one bill for 400+ models
          across every major provider. Cost, fallback, and provider
          diversity — one place. That is the surface a policy engine
          should sit on.
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          Guard treats OpenRouter as a first-class upstream. Set it
          once in your workspace proxy config; every LLM call your
          tools make routes through Guard first, then out to OpenRouter,
          then on to whichever model the request named. Same rules
          apply whether the call ends up at Claude Opus or DeepSeek V3.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The whole configuration</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Open <code>/settings/proxy</code> in the Conduct console.
          Paste OpenRouter as your upstream, drop in your OpenRouter
          key, save, push to an environment.
        </p>
        <pre className="bg-stone-950 text-stone-100 p-6 rounded-2xl overflow-x-auto text-sm font-mono leading-relaxed mb-6">
{`LLM Upstream:          https://openrouter.ai/api/v1
LLM Upstream API Key:  sk-or-...`}
        </pre>
        <p className="text-stone-700 leading-relaxed mb-4">
          Point your tools at the Conduct Proxy URL as{" "}
          <code>ANTHROPIC_BASE_URL</code> or <code>OPENAI_BASE_URL</code>.
          Guard detects the OpenRouter host, rewrites the model ID to
          OpenRouter's <code>provider/model</code> convention (e.g.{" "}
          <code>anthropic/claude-3-5-haiku</code>), attaches attribution
          headers, and forwards. Verdicts come back as Allow, Audit,
          Warn, Block, or Pending human-in-the-loop approval. On block,
          the upstream call never fires.{" "}
          <strong>Zero OpenRouter credits spent on policy-violating
          traffic.</strong>
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Why this matters if you already use OpenRouter</h2>
        <ul className="text-stone-700 leading-relaxed mb-6 list-disc pl-6 space-y-3">
          <li>
            <strong>Model-agnostic policy.</strong> A prompt-injection
            rule you write once applies whether the request routes to
            GPT-4o, Claude, Gemini, or a Llama variant on Together.
            OpenRouter picks the model; Guard decides whether it runs
            at all.
          </li>
          <li>
            <strong>Signed configuration.</strong> Every workspace
            signs its active policy set. Every check verifies the
            signature before enforcing. A tampered pack is rejected
            before it can decide anything.
          </li>
          <li>
            <strong>Hash-chained audit.</strong> Every decision appends
            to a SHA-256 chain rooted at workspace genesis. Missing or
            altered entries break the chain and are caught on one-click
            verification. Evidence you can hand to an auditor.
          </li>
          <li>
            <strong>20+ compliance packs out of the box.</strong>{" "}
            OWASP, SOC 2 CC7.3, HIPAA §164.312, PCI DSS 4.0, EU AI Act
            Art. 15/16, NIST AI RMF, ISO 42001. Turn them on, they
            enforce on every OpenRouter call.
          </li>
          <li>
            <strong>Human-in-the-loop approvals.</strong> Any rule with{" "}
            <code>action: approval</code> pauses the request, posts to
            Slack with Approve and Reject buttons, and resumes on
            decision — even on the higher-cost model route where you
            most want a checkpoint.
          </li>
        </ul>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Try it in five minutes</h2>
        <ol className="text-stone-700 leading-relaxed mb-6 list-decimal pl-6 space-y-2">
          <li>Open <code>/settings/proxy</code> in the Conduct console.</li>
          <li>Set <strong>LLM Upstream</strong> to <code>https://openrouter.ai/api/v1</code>.</li>
          <li>Paste your OpenRouter key into <strong>LLM Upstream API Key</strong>. Save.</li>
          <li>Push to your environment.</li>
          <li>
            Export the Conduct Proxy URL as <code>ANTHROPIC_BASE_URL</code> /{" "}
            <code>OPENAI_BASE_URL</code> in the tool you want to route.
          </li>
        </ol>
        <p className="text-stone-700 leading-relaxed mb-6">
          Verify in the console at <code>/theguard/activity</code> —
          every request lands as an audit row within seconds, tagged
          with the OpenRouter target model.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Which gateway is right</h2>
        <p className="text-stone-700 leading-relaxed mb-8">
          Guard supports Portkey, OpenRouter, Helicone, LiteLLM, and
          Azure OpenAI as upstreams, plus a generic OpenAI-compatible
          fallback. Pick the one you already run. The Guard policy
          layer is the same either way — one ruleset, every surface.
        </p>

        <div className="not-prose flex flex-wrap gap-3 mt-12 mb-8">
          <a
            href="/router"
            className="inline-flex items-center gap-2 rounded-lg bg-stone-900 text-white px-5 py-3 text-sm font-semibold hover:bg-stone-800 transition-colors"
          >
            Router landing
          </a>
          <a
            href="/settings/proxy"
            className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white text-stone-700 px-5 py-3 text-sm font-semibold hover:border-stone-300 hover:shadow-sm transition-all"
          >
            Open proxy settings
          </a>
        </div>

        <div className="mt-16 pt-8 border-t border-stone-200">
          <CtaLink className="inline-flex items-center gap-2 rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors" />
        </div>
      </div>
    </article>
  )
}
