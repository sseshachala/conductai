import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "LiteLLM sends AI requests. Conduct decides which ones shouldn't be sent. | Conduct",
  description:
    "If you use LiteLLM already, you have a router. Plug Conduct into it and you have a policy layer that runs before every request — six things you can't do with LiteLLM alone.",
}

export default function BlogPost() {
  return (
    <article className="max-w-3xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-orange-700 bg-orange-50 border border-orange-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Integrations
          </span>
          <span className="text-xs text-stone-400">September 12, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          LiteLLM sends AI requests. Conduct decides which ones shouldn&apos;t be sent.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          If you use LiteLLM already, you have a router. Plug Conduct
          into it and you have a policy layer that runs before every
          request — without changing anything else about your setup.
        </p>
      </div>

      {/* Flow diagram: agents → LiteLLM → Conduct guardrail → models */}
      <div className="not-prose mb-10 rounded-xl overflow-hidden border border-stone-200 shadow-sm bg-stone-950">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/blog/conduct-litellm-guard-flow.svg"
          alt="Conduct as a pre-call guardrail inside LiteLLM: your app calls LiteLLM, LiteLLM asks Conduct for a verdict, allowed requests continue to the model provider, blocked requests get a structured error."
          className="w-full h-auto"
        />
      </div>

      {/* Demo video */}
      <div className="not-prose mb-12">
        <div className="rounded-xl overflow-hidden border border-stone-200 shadow-sm" style={{ position: "relative", paddingBottom: "56.25%", height: 0 }}>
          <iframe
            src="https://www.youtube.com/embed/pdInsCrqkss"
            title="Conduct Guard × LiteLLM — one YAML block, live policy enforcement"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
            style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", border: 0 }}
          />
        </div>
        <p className="text-xs text-stone-400 mt-3 text-center">
          LiteLLM proxy with{" "}
          <code className="text-stone-500">guardrail: conduct</code>{" "}
          blocking a policy-violating request in real time.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">
        <h2 className="text-2xl font-bold text-stone-900 mt-4 mb-4">What LiteLLM does</h2>
        <p className="text-stone-700 leading-relaxed">
          <a
            href="https://www.litellm.ai"
            className="text-orange-700 underline"
            target="_blank"
            rel="noopener"
          >
            LiteLLM
          </a>{" "}
          is the middleman between your code and the model providers.
          Your app says &ldquo;call an AI&rdquo;; LiteLLM figures out
          whether that means OpenAI, Claude, Gemini, or a fallback if
          the first one is down. It tracks how much you spent. It
          handles rate limits. It is very good at that job.
        </p>
        <p className="text-stone-700 leading-relaxed">
          But LiteLLM doesn&apos;t decide{" "}
          <strong>whether the request should happen at all.</strong>{" "}
          That&apos;s the gap Conduct fills.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What Conduct adds</h2>
        <p className="text-stone-700 leading-relaxed">
          {/* .mkt-inline-link opts out of the marketing CTA pill
              styling defined in globals.css so this inline mention
              renders as a plain hyperlink. */}
          <a
            href="/sign-up"
            className="mkt-inline-link text-orange-700 underline"
          >
            Conduct
          </a>{" "}
          plugs into LiteLLM as a guardrail. Every request LiteLLM is
          about to send goes through Conduct first. Conduct checks it
          against your policy rules and answers:{" "}
          <strong>yes send it, send it with a warning, or no,
          don&apos;t send it.</strong>
        </p>
        <p className="text-stone-700 leading-relaxed">
          Six things you can&apos;t do with LiteLLM alone but you can
          do with Conduct plugged in:
        </p>

        <h3 className="text-xl font-bold text-stone-900 mt-8 mb-3">
          1. Stop bad requests before they reach the model.
        </h3>
        <p className="text-stone-700 leading-relaxed">
          Someone tries to make your agent leak credentials or exfil
          data. LiteLLM ships the request and pays for it. Conduct
          blocks it with a specific rule id so the developer knows
          why and how to fix it. Same pattern for prompt-injection
          attempts, unsafe tool-call arguments, or anything else your
          policy calls out.
        </p>

        <h3 className="text-xl font-bold text-stone-900 mt-8 mb-3">
          2. Enforce spending limits as a hard block, not just a report.
        </h3>
        <p className="text-stone-700 leading-relaxed">
          LiteLLM tracks that developer X spent $50 this month. That&apos;s
          a report. Conduct is what actually stops their next request
          when they cross the workspace or per-developer cap you
          configured. LiteLLM knows what happened. Conduct changes what
          happens next.
        </p>

        <h3 className="text-xl font-bold text-stone-900 mt-8 mb-3">
          3. Write your own rules.
        </h3>
        <p className="text-stone-700 leading-relaxed">
          &ldquo;Every prompt from the finance team must be blocked if
          it mentions a customer name.&rdquo; LiteLLM has no place to
          express that. Conduct is a policy engine — you write the rule
          once in YAML, it enforces on every call. Ship it to your
          whole team by pushing to the workspace policy repo.
        </p>

        <h3 className="text-xl font-bold text-stone-900 mt-8 mb-3">
          4. See what happened in one triage view.
        </h3>
        <p className="text-stone-700 leading-relaxed">
          LiteLLM writes logs. Conduct dedups them into an Inbox:{" "}
          <em>this rule fired 247 times this week, mostly from three
          developers, click here to see the prompts and resolve.</em>{" "}
          One place your security lead checks in the morning instead
          of grepping log files.
        </p>

        <h3 className="text-xl font-bold text-stone-900 mt-8 mb-3">
          5. Prove what happened — cryptographically.
        </h3>
        <p className="text-stone-700 leading-relaxed">
          Every audit event Conduct writes is chained to the previous
          one with a hash. If somebody edits history, chain
          verification fails and Conduct tells you the exact row where
          it broke. LiteLLM&apos;s logs don&apos;t do that. Auditors
          care about this. So do you the day something goes wrong and
          the question is who deleted what.
        </p>

        <h3 className="text-xl font-bold text-stone-900 mt-8 mb-3">
          6. Same rules everywhere.
        </h3>
        <p className="text-stone-700 leading-relaxed">
          Conduct also runs as a proxy in front of raw LLM calls, as
          an MCP hook for Claude Code and Cursor, and as a CLI. The
          rule you write for LiteLLM is the same rule that catches the
          same request in a developer&apos;s terminal. LiteLLM covers
          one surface. Conduct covers all of them from one policy.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Turning it on</h2>
        <p className="text-stone-700 leading-relaxed">
          Install the plugin:
        </p>
        <pre className="not-prose bg-stone-900 text-stone-100 px-5 py-4 rounded-lg text-sm overflow-x-auto mt-6">
{`pip install conduct-litellm-guard>=0.2.5`}
        </pre>
        <p className="text-stone-700 leading-relaxed">
          Add this block to your LiteLLM config:
        </p>
        <pre className="not-prose bg-stone-900 text-stone-100 px-5 py-4 rounded-lg text-sm overflow-x-auto mt-6">
{`guardrails:
  - guardrail_name: conduct
    litellm_params:
      guardrail: conduct
      mode: pre_call
      api_key: os.environ/CONDUCT_AGENT_TOKEN
      api_base: os.environ/CONDUCT_API_URL
      workspace_id: os.environ/CONDUCT_WORKSPACE_ID
      timeout: 8.0
      unreachable_fallback: fail_closed`}
        </pre>
        <p className="text-stone-700 leading-relaxed">
          Restart LiteLLM. Done. Every request now runs through your
          policy before it leaves your network.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          If you were already using our plugin
        </h2>
        <p className="text-stone-700 leading-relaxed">
          Upgrade to 0.2.5. Older versions had a bug where a config
          setting could silently do the opposite of what you
          configured. The new version refuses to install if you&apos;re
          on the broken one.
        </p>
        <pre className="not-prose bg-stone-900 text-stone-100 px-5 py-4 rounded-lg text-sm overflow-x-auto mt-6">
{`pip install --upgrade "conduct-litellm-guard>=0.2.5"`}
        </pre>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What&apos;s next</h2>
        <p className="text-stone-700 leading-relaxed">
          Same integration coming for NeMo Guardrails and
          Guardrails-AI. Same rules, one policy layer, wherever your
          team put their model traffic.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Get started</h2>
        <div className="not-prose flex flex-wrap gap-3 mt-4 mb-8">
          <a
            href="/sign-up"
            className="inline-flex items-center gap-2 rounded-lg bg-stone-900 text-white px-5 py-3 text-sm font-semibold hover:bg-stone-800 transition-colors"
          >
            Sign up for Conduct — free
          </a>
          <a
            href="https://pypi.org/project/conduct-litellm-guard/"
            target="_blank"
            rel="noopener"
            className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white text-stone-700 px-5 py-3 text-sm font-semibold hover:border-stone-300 hover:shadow-sm transition-all"
          >
            Plugin on PyPI
          </a>
          <a
            href="https://docs.litellm.ai/docs/proxy/guardrails/conduct"
            target="_blank"
            rel="noopener"
            className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white text-stone-700 px-5 py-3 text-sm font-semibold hover:border-stone-300 hover:shadow-sm transition-all"
          >
            LiteLLM docs
          </a>
          <a
            href="https://github.com/BerriAI/litellm"
            target="_blank"
            rel="noopener"
            className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white text-stone-700 px-5 py-3 text-sm font-semibold hover:border-stone-300 hover:shadow-sm transition-all"
          >
            LiteLLM on GitHub
          </a>
        </div>

        <div className="mt-16 pt-8 border-t border-stone-200">
          <CtaLink className="inline-flex items-center gap-2 rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors" />
        </div>
      </div>
    </article>
  )
}
