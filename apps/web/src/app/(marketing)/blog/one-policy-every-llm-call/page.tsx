import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "One policy for every LLM call — Conduct Guard now ships as a LiteLLM plugin | Conduct",
  description:
    "Add a Guard rule once. Every LLM call routed through your LiteLLM proxy — from any provider, any coding agent, any customer app — enforces it before the request leaves your network.",
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
          One policy for every LLM call.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          Conduct Guard now runs as a LiteLLM plugin. Add a rule once —
          every LLM call routed through your LiteLLM proxy enforces it
          before the request leaves your network.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">
        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Why LiteLLM</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          If your team runs LiteLLM, you have already made a decision:
          LLM traffic flows through a single control plane. Cost
          tracking, key rotation, model routing, provider fallback —
          one place. That is exactly the surface a policy engine
          should sit on.
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          Today we are shipping{" "}
          <a
            href="https://pypi.org/project/conduct-litellm-guard/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 hover:underline"
          >
            <code>conduct-litellm-guard</code>
          </a>{" "}
          — Conduct Guard as a LiteLLM <code>CustomGuardrail</code>.
          One <code>pip install</code>, one config block, every LLM
          call routed through LiteLLM runs through your active Conduct
          packs.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The whole integration</h2>
        <pre className="bg-stone-950 text-stone-100 p-6 rounded-2xl overflow-x-auto text-sm font-mono leading-relaxed mb-6">
{`guardrails:
  - guardrail_name: conduct-guard
    litellm_params:
      guardrail: conduct_litellm_guard.ConductGuard
      agent_token: os.environ/CONDUCT_AGENT_TOKEN
      fail_mode: fail_closed`}
        </pre>
        <p className="text-stone-700 leading-relaxed mb-4">
          That is the whole thing. Every call hitting your LiteLLM
          proxy — regardless of upstream provider — routes through
          Guard. Verdicts come back as Allow, Audit, Warn, Block, or
          Pending human-in-the-loop approval. On block, LiteLLM
          returns 400 with the rule name and message.{" "}
          <strong>Zero upstream tokens spent on policy-violating
          traffic.</strong>
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What Guard adds on top of a firewall-style guardrail</h2>
        <ul className="text-stone-700 leading-relaxed mb-6 list-disc pl-6 space-y-3">
          <li>
            <strong>Signed configuration.</strong> Every workspace
            signs its active policy set. Every check verifies the
            signature before enforcing. A tampered pack, pushed at any
            layer, is rejected before it can decide anything.
          </li>
          <li>
            <strong>Hash-chained audit.</strong> Every decision appends
            to a SHA-256 chain rooted at workspace genesis. Missing or
            altered entries break the chain and are caught on
            one-click verification. Evidence you can hand to an
            auditor.
          </li>
          <li>
            <strong>20+ compliance packs out of the box.</strong>{" "}
            OWASP, SOC 2 CC7.3, HIPAA §164.312, PCI DSS 4.0, EU AI Act
            Art. 15/16, NIST AI RMF, ISO 42001. Turn them on, they
            enforce everywhere Guard runs.
          </li>
          <li>
            <strong>Human-in-the-loop approvals.</strong> Any rule with{" "}
            <code>action: approval</code> pauses the request, posts to
            Slack with Approve and Reject buttons, and resumes on
            decision. The plugin surfaces the pause to LiteLLM as a
            structured error.
          </li>
          <li>
            <strong>Cross-tool coverage.</strong> The same policy
            already enforces on Claude Code, Cursor, Copilot, and
            Codex sessions via the CLI hook and MCP layers. Adding
            LiteLLM makes it four enforcement surfaces sharing one
            ruleset.
          </li>
        </ul>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Try it in five minutes</h2>
        <pre className="bg-stone-950 text-stone-100 p-6 rounded-2xl overflow-x-auto text-sm font-mono leading-relaxed mb-6">
{`pip install conduct-litellm-guard`}
        </pre>
        <p className="text-stone-700 leading-relaxed mb-4">
          Add the guardrail block above to your <code>config.yaml</code>,
          export <code>CONDUCT_AGENT_TOKEN</code>, restart LiteLLM.
          Every call now goes through Guard. Verify in the Conduct
          console at <code>/theguard/activity</code> — every request
          lands as an audit row within seconds.
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          Every response you can get maps deterministically to a
          specific cause and fix.{" "}
          <a
            href="https://github.com/sseshachala/conductai/tree/main/packages/conduct-litellm-guard"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 hover:underline"
          >
            The full response-to-cause-to-fix table lives in the plugin README.
          </a>
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Source and license</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          The plugin lives under{" "}
          <a
            href="https://github.com/sseshachala/conductai/tree/main/packages/conduct-litellm-guard"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 hover:underline"
          >
            <code>packages/conduct-litellm-guard/</code>
          </a>{" "}
          in our main repo. Licensed FSL-1.1-MIT — free for internal
          use, non-competing commercial use, and professional services.
          Converts to MIT on 2028-08-23.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What is next</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          We are contributing the adapter upstream to{" "}
          <code>BerriAI/litellm</code> so it lands in the official
          guardrails list alongside Aporia, Lakera, Bedrock Guardrails,
          and Presidio. The standalone package remains for teams on
          pinned older LiteLLM versions.
        </p>

        <p className="text-stone-700 leading-relaxed mb-8">
          Runtime firewalls tell you what happened. Guard controls what
          can happen — with cryptographic proof. Now on every LiteLLM
          proxy.
        </p>

        <div className="not-prose flex flex-wrap gap-3 mt-12 mb-8">
          <a
            href="https://pypi.org/project/conduct-litellm-guard/"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-stone-900 text-white px-5 py-3 text-sm font-semibold hover:bg-stone-800 transition-colors"
          >
            View on PyPI
          </a>
          <a
            href="https://github.com/sseshachala/conductai/tree/main/packages/conduct-litellm-guard"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white text-stone-700 px-5 py-3 text-sm font-semibold hover:border-stone-300 hover:shadow-sm transition-all"
          >
            View source
          </a>
          <a
            href="/router"
            className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white text-stone-700 px-5 py-3 text-sm font-semibold hover:border-stone-300 hover:shadow-sm transition-all"
          >
            Router landing
          </a>
        </div>

        <div className="mt-16 pt-8 border-t border-stone-200">
          <CtaLink className="inline-flex items-center gap-2 rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors" />
        </div>
      </div>
    </article>
  )
}
