"use client"

import { useState } from "react"

export default function RouterLandingPage() {
  return (
    <>
      <HeroSection />
      <PrimitivesSection />
      <TwoPathsSection />
      <UsageSection />
      <SetupSection />
      <GuardRelationSection />
      <FinalCTASection />
    </>
  )
}

/* ─── Hero ─────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        Conduct Router
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        Every LLM call, governed<br />
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">before the request leaves your network.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-4">
        Router is a Guard-aware LLM proxy. Point any SDK at it — Anthropic, OpenAI, Perplexity — and every call runs through policy before it hits the upstream provider.
      </p>
      <p className="text-base text-stone-600 max-w-2xl mx-auto leading-relaxed mb-8">
        Per-agent tokens, provider fallback, retry on upstream error, spend metering, hash-chained audit. One drop-in URL swap for your existing code.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <a href="/docs" className="inline-flex items-center gap-2 bg-stone-900 text-white rounded-lg px-5 py-3 text-sm font-semibold hover:bg-stone-800 transition-colors">
          Read the docs
        </a>
        <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 border border-stone-200 rounded-lg px-5 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all">
          View source
        </a>
      </div>
    </section>
  )
}

/* ─── What it does ─────────────────────────────────────────────────────── */

function PrimitivesSection() {
  const items = [
    {
      title: "Per-agent tokens",
      body: "Every agent gets its own cond_agt_* bearer minted at run start. Rotate on demand, scope to a workflow, revoke without touching upstream keys.",
    },
    {
      title: "Provider fallback",
      body: "Configure a primary and one or more fallbacks. If Anthropic rate-limits or 500s, Router retries against OpenAI or Perplexity within the same request, transparent to the caller.",
    },
    {
      title: "Retry on upstream error",
      body: "Structured LLMUpstreamError classification with exponential backoff. Retries survive transient 429/500/network errors so a flaky provider doesn't fail your agent.",
    },
    {
      title: "Hash-chained audit",
      body: "Every request/response pair is logged with the active policy hash, agent identity, spend, and provider. Chain is append-only and verifiable — proof of governance for auditors.",
    },
  ]

  return (
    <section className="max-w-5xl mx-auto px-6 py-16">
      <h2 className="text-3xl font-black tracking-tight text-stone-900 mb-3 text-center">
        Four primitives, one proxy
      </h2>
      <p className="text-stone-500 text-center max-w-2xl mx-auto mb-12">
        Every Router feature exists because a real agent broke on it in production.
      </p>
      <div className="grid md:grid-cols-2 gap-6">
        {items.map((it) => (
          <div key={it.title} className="border border-stone-200 rounded-xl p-6 bg-white">
            <h3 className="text-lg font-bold text-stone-900 mb-2">{it.title}</h3>
            <p className="text-sm text-stone-600 leading-relaxed">{it.body}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ─── Two paths ────────────────────────────────────────────────────────── */

function TwoPathsSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-16 bg-stone-50 rounded-2xl">
      <h2 className="text-3xl font-black tracking-tight text-stone-900 mb-3 text-center">
        Two ways to route through Conduct
      </h2>
      <p className="text-stone-500 text-center max-w-2xl mx-auto mb-12">
        Same policy engine, two integration points. Pick based on what your stack already runs.
      </p>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Option 1: Conduct Router */}
        <div className="border border-stone-200 rounded-xl bg-white p-6 flex flex-col">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700">
              Native
            </span>
            <span className="text-xs text-stone-500">Best for greenfield</span>
          </div>
          <h3 className="text-xl font-bold text-stone-900 mb-2">Conduct Router</h3>
          <p className="text-sm text-stone-600 leading-relaxed mb-4">
            Point any provider SDK at <code className="text-stone-800 text-xs">api.conductai.ai/proxy/&lt;provider&gt;</code>.
            No new infrastructure — Router speaks each provider&apos;s native API, per-agent tokens, retries, and audit
            chain out of the box.
          </p>
          <div className="bg-stone-950 rounded-lg p-3 mb-4">
            <pre className="text-xs font-mono text-stone-100 overflow-x-auto">
{`export ANTHROPIC_BASE_URL=\\
  https://api.conductai.ai/proxy/anthropic
export ANTHROPIC_API_KEY=cond_agt_...`}
            </pre>
          </div>
          <ul className="text-xs text-stone-500 space-y-1 leading-relaxed">
            <li>Provider fallback + retries baked in</li>
            <li>Spend metering per agent token</li>
            <li>One URL swap in your app</li>
          </ul>
        </div>

        {/* Option 2: LiteLLM plugin */}
        <div className="border border-stone-200 rounded-xl bg-white p-6 flex flex-col">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full bg-orange-100 text-orange-700">
              Plugin
            </span>
            <span className="text-xs text-stone-500">Best if you already run LiteLLM</span>
          </div>
          <h3 className="text-xl font-bold text-stone-900 mb-2">LiteLLM + Guard plugin</h3>
          <p className="text-sm text-stone-600 leading-relaxed mb-4">
            Keep your LiteLLM proxy. Install{" "}
            <code className="text-stone-800 text-xs">conduct-litellm-guard</code> — every call through LiteLLM
            policy-checks against your active Conduct packs before the upstream request goes out.
          </p>

          <p className="text-[11px] font-semibold uppercase tracking-widest text-stone-400 mb-2">
            Explicit form — any LiteLLM version
          </p>
          <div className="bg-stone-950 rounded-lg p-3 mb-3">
            <pre className="text-xs font-mono text-stone-100 overflow-x-auto">
{`# config.yaml
guardrails:
  - guardrail_name: conduct-guard
    litellm_params:
      guardrail: conduct_litellm_guard.ConductGuard
      agent_token: os.environ/CONDUCT_AGENT_TOKEN`}
            </pre>
          </div>

          <p className="text-[11px] font-semibold uppercase tracking-widest text-stone-400 mb-2">
            Native form —{" "}
            <a
              href="https://github.com/BerriAI/litellm/pull/38143"
              target="_blank"
              rel="noopener noreferrer"
              className="text-indigo-600 hover:underline normal-case tracking-normal"
            >
              once BerriAI PR #38143 merges
            </a>
          </p>
          <div className="bg-stone-950 rounded-lg p-3 mb-4">
            <pre className="text-xs font-mono text-stone-100 overflow-x-auto">
{`guardrails:
  - guardrail_name: conduct-guard
    litellm_params:
      guardrail: conduct
      api_key: os.environ/CONDUCT_AGENT_TOKEN`}
            </pre>
          </div>

          <ul className="text-xs text-stone-500 space-y-1 leading-relaxed">
            <li><code className="text-stone-700">pip install conduct-litellm-guard</code> (both forms)</li>
            <li>No infrastructure change to your LiteLLM setup</li>
            <li>
              <a
                href="https://github.com/sseshachala/conductai/tree/main/packages/conduct-litellm-guard"
                className="text-indigo-600 hover:underline"
                target="_blank"
                rel="noopener noreferrer"
              >
                View plugin source
              </a>
            </li>
          </ul>
        </div>
      </div>

      <p className="text-xs text-stone-500 text-center mt-8 max-w-3xl mx-auto leading-relaxed">
        Both paths hit the same policy engine, the same signed configuration, and the same hash-chained audit log.
        Same enforcement, same evidence — different entry points.
      </p>
    </section>
  )
}

/* ─── Usage ────────────────────────────────────────────────────────────── */

function UsageSection() {
  const [tab, setTab] = useState<"curl" | "python" | "ts">("curl")
  const samples = {
    curl: `curl https://api.conductai.ai/proxy/anthropic/v1/messages \\
  -H "Authorization: Bearer cond_agt_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "claude-sonnet-4-6",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello"}]
  }'`,
    python: `from anthropic import Anthropic

client = Anthropic(
    base_url="https://api.conductai.ai/proxy/anthropic",
    api_key="cond_agt_...",   # agent token, not the raw Anthropic key
)
msg = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)`,
    ts: `import Anthropic from "@anthropic-ai/sdk"

const client = new Anthropic({
  baseURL: "https://api.conductai.ai/proxy/anthropic",
  apiKey: process.env.CONDUCT_AGENT_TOKEN!,
})
const msg = await client.messages.create({
  model: "claude-sonnet-4-6",
  max_tokens: 1024,
  messages: [{ role: "user", content: "Hello" }],
})`,
  }

  return (
    <section className="max-w-5xl mx-auto px-6 py-16">
      <h2 className="text-3xl font-black tracking-tight text-stone-900 mb-3 text-center">
        Swap one URL. Nothing else changes.
      </h2>
      <p className="text-stone-500 text-center max-w-2xl mx-auto mb-8">
        Router speaks each provider&apos;s native API. Your existing SDKs work unchanged — you point them at Router instead of the upstream host.
      </p>
      <div className="border border-stone-200 rounded-xl overflow-hidden bg-white">
        <div className="flex border-b border-stone-200">
          {(["curl", "python", "ts"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`px-5 py-3 text-sm font-semibold transition-colors ${
                tab === k
                  ? "text-stone-900 border-b-2 border-indigo-600"
                  : "text-stone-500 hover:text-stone-700"
              }`}
            >
              {k === "curl" ? "curl" : k === "python" ? "Python" : "TypeScript"}
            </button>
          ))}
        </div>
        <pre className="bg-stone-950 text-stone-100 p-6 overflow-x-auto text-sm font-mono leading-relaxed">
          <code>{samples[tab]}</code>
        </pre>
      </div>
      <p className="text-xs text-stone-500 text-center mt-4">
        Endpoints: <code className="text-stone-700">/proxy/anthropic/v1/messages</code>,{" "}
        <code className="text-stone-700">/proxy/openai/v1/chat/completions</code>,{" "}
        <code className="text-stone-700">/proxy/perplexity/chat/completions</code>
      </p>
    </section>
  )
}

/* ─── Setup ────────────────────────────────────────────────────────────── */

function SetupSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-16 bg-stone-50 rounded-2xl">
      <h2 className="text-3xl font-black tracking-tight text-stone-900 mb-3 text-center">
        Two minutes to running
      </h2>
      <p className="text-stone-500 text-center max-w-2xl mx-auto mb-10">
        Self-host with the same repo as Guard, or use the hosted endpoint.
      </p>
      <div className="grid md:grid-cols-2 gap-6 max-w-4xl mx-auto">
        <div className="bg-white border border-stone-200 rounded-xl p-6">
          <div className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">
            Self-host
          </div>
          <pre className="bg-stone-950 text-stone-100 p-4 rounded-lg text-xs font-mono overflow-x-auto">
{`git clone https://github.com/sseshachala/conductai
cd conductai
docker compose up`}
          </pre>
          <p className="text-sm text-stone-600 mt-4 leading-relaxed">
            Router listens on port 8000 under <code className="text-stone-800">/proxy/*</code>. Point your provider SDKs at <code className="text-stone-800">http://localhost:8000/proxy/&lt;provider&gt;</code>.
          </p>
        </div>
        <div className="bg-white border border-stone-200 rounded-xl p-6">
          <div className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">
            Hosted
          </div>
          <pre className="bg-stone-950 text-stone-100 p-4 rounded-lg text-xs font-mono overflow-x-auto">
{`export ANTHROPIC_BASE_URL=\\
  https://api.conductai.ai/proxy/anthropic
export ANTHROPIC_API_KEY=cond_agt_...`}
          </pre>
          <p className="text-sm text-stone-600 mt-4 leading-relaxed">
            Mint an agent token in the console. The token owns which Guard packs, spend cap, and provider list apply.
          </p>
        </div>
      </div>
    </section>
  )
}

/* ─── Relation to Guard ────────────────────────────────────────────────── */

function GuardRelationSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-16">
      <div className="border border-stone-200 rounded-xl p-8 bg-white">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-base">🛡️</span>
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-500">
            How Router relates to Guard
          </p>
        </div>
        <h2 className="text-2xl font-black tracking-tight text-stone-900 mb-4">
          Router is where Guard enforces.
        </h2>
        <p className="text-stone-600 leading-relaxed mb-4">
          Guard is the policy engine — packs, personas, and hash chain. Router is the point where those policies run. Every LLM call that arrives at Router is checked against the active packs before the upstream request goes out.
        </p>
        <p className="text-stone-600 leading-relaxed mb-4">
          If a policy blocks, the caller gets a structured 403 with the rule name and remediation hint — no upstream token spent. If a policy warns, the call proceeds and the audit chain records it. If it&apos;s allowed, Router forwards with a full audit entry: agent identity, active pack hash, latency, tokens, spend.
        </p>
        <p className="text-stone-500 text-sm leading-relaxed">
          You can run Router without Guard (drop the packs, it becomes a plain observable proxy). You can run Guard without Router (Guard also enforces on the CLI hook and MCP layers). But together they cover every path an agent uses to reach a model.
        </p>
      </div>
    </section>
  )
}

/* ─── Final CTA ────────────────────────────────────────────────────────── */

function FinalCTASection() {
  return (
    <section className="border-t border-stone-200 bg-stone-50 px-6 py-16">
      <div className="max-w-5xl mx-auto text-center">
        <h2 className="text-3xl font-black tracking-tight text-stone-900 mb-4">
          Route your agents through Conduct.
        </h2>
        <p className="text-stone-500 max-w-xl mx-auto mb-8">
          Same repo as Guard. Same license. One <code className="text-stone-800">docker compose up</code>.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <a href="/docs" className="inline-flex items-center gap-2 bg-stone-900 text-white rounded-lg px-5 py-3 text-sm font-semibold hover:bg-stone-800 transition-colors">
          Read the docs
        </a>
          <a
            href="https://github.com/sseshachala/conductai"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 border border-stone-200 rounded-lg px-5 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all bg-white"
          >
            GitHub
          </a>
        </div>
      </div>
    </section>
  )
}
