import Link from "next/link"
import { ThreatModelRow } from "@/components/marketing/facelift/ThreatModelRow"

export const metadata = {
  title: "Security — Conduct",
  description:
    "How Guard enforces, evidences, and where its threat model draws the line. Runtime policy across every agent tool your team runs.",
}

export default function SecurityPage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-4xl mx-auto px-6 py-20">
        <section className="mb-16 text-center">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
            Security
          </p>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
            One policy where your stack isn&apos;t one vendor&apos;s.
          </h1>
          <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed">
            Cortex enforces inside Cortex. Copilot Studio inside Copilot. Bedrock inside Bedrock. Conduct enforces across whatever mix your team runs — with a scope you can inspect.
          </p>
        </section>

        <section className="mb-16">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Enforcement</h2>
          <p className="text-stone-600 leading-relaxed mb-5">
            Guard evaluates every action against your policy before it executes. Three enforcement surfaces catch every path an agent can take:
          </p>
          <ul className="text-sm text-stone-600 space-y-2.5">
            <li className="flex items-start gap-3">
              <span className="text-stone-400 font-mono shrink-0 min-w-[48px] pt-0.5">CLI</span>
              <span>Post-tool-use hook on Claude Code, Cursor, Codex, Copilot. Local decisions, no round-trip.</span>
            </li>
            <li className="flex items-start gap-3">
              <span className="text-stone-400 font-mono shrink-0 min-w-[48px] pt-0.5">HTTP</span>
              <span>Drop-in base URL replacement in front of your model gateway. Every LLM request is policy-checked.</span>
            </li>
            <li className="flex items-start gap-3">
              <span className="text-stone-400 font-mono shrink-0 min-w-[48px] pt-0.5">MCP</span>
              <span>Wraps MCP tool invocations before they reach the server. Same policy engine, different transport.</span>
            </li>
          </ul>
        </section>

        <section className="mb-16 border-t border-stone-100 pt-12">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Evidence</h2>
          <p className="text-stone-600 leading-relaxed mb-4">
            Every decision is a receipt. Hash-chained (SHA-256) so tampering is detectable, exportable by policy, and answerable to auditors.
          </p>
          <Link
            href="/evidence"
            className="text-sm font-semibold text-stone-900 hover:text-stone-600"
          >
            See what a receipt contains →
          </Link>
        </section>

        <section className="mb-16 border-t border-stone-100 pt-12">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Rollout</h2>
          <p className="text-stone-600 leading-relaxed mb-4">
            Run Guard as SaaS, in a container, on Kubernetes, or fully isolated. Same policy engine, same audit trail, wherever your data must stay.
          </p>
          <Link
            href="/deployment"
            className="text-sm font-semibold text-stone-900 hover:text-stone-600"
          >
            See rollout options →
          </Link>
        </section>

        <section className="mb-16 border-t border-stone-100 pt-12">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Threat model</h2>
          <p className="text-stone-600 leading-relaxed mb-6">
            We publish where Guard stops. Honest scope is a design requirement — and a differentiator, because heterogeneous coverage means we can&apos;t pretend to own every layer.
          </p>
          <div className="border border-stone-200 rounded-2xl overflow-hidden">
            <div className="px-5 py-3 bg-stone-50 border-b border-stone-200">
              <p className="text-xs font-mono font-bold text-stone-600 uppercase tracking-wider">
                Coverage map
              </p>
            </div>
            <div className="px-5 py-2">
              <ThreatModelRow
                threat="Actions routed through Guard (CLI hook, HTTP proxy, MCP layer)"
                coverage="Protected"
                detail="All three surfaces run the same policy engine. Refunds, network changes, secret reads — every action routed through Guard is inspected."
              />
              <ThreatModelRow
                threat="Audit trail integrity"
                coverage="Protected"
                detail="SHA-256 hash chain on every decision. Altered entries break verification."
              />
              <ThreatModelRow
                threat="Pre-call prompt injection (before Guard sees the tool call)"
                coverage="Partial"
                detail="Injection detection pack + pattern-based checks. ML-based detection is not implemented."
              />
              <ThreatModelRow
                threat="Model-layer attacks (adversarial inputs to the LLM itself)"
                coverage="Partial"
                detail="Prompt-injection pack included. Semantic ML detection not implemented."
              />
              <ThreatModelRow
                threat="Cross-agent correlation (Operations context)"
                coverage="Not protected"
                detail="Guard evaluates each action in isolation today. Cross-agent context is the Operations gap — Design Partner Preview."
              />
              <ThreatModelRow
                threat="Actions that bypass all three enforcement surfaces"
                coverage="Not protected"
                detail="An agent that does not use the hook, proxy, or MCP layer is invisible to Guard."
              />
            </div>
          </div>
        </section>

        <section className="mb-16 border-t border-stone-100 pt-12">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Trust &amp; compliance</h2>
          <p className="text-stone-600 leading-relaxed mb-8">
            What&apos;s certified, who touches your data, and how it&apos;s handled. Enterprise buyers
            paste this into their security review packet.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-8">
            {/* Compliance & attestations */}
            <div className="rounded-2xl border border-stone-200 bg-white p-6">
              <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-3">
                Compliance &amp; attestations
              </p>
              <p className="text-sm text-stone-600 leading-relaxed">
                Certifications in progress. Letter of intent and gap-analysis timeline available on
                request — email{" "}
                <a href="mailto:security@conductai.ai" className="text-stone-900 font-semibold hover:underline">
                  security@conductai.ai
                </a>
                .
              </p>
            </div>

            {/* Data handling */}
            <div className="rounded-2xl border border-stone-200 bg-white p-6">
              <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-3">
                Data handling
              </p>
              <ul className="text-sm text-stone-600 space-y-2 leading-relaxed">
                <li>
                  <span className="font-semibold text-stone-900">Stored:</span> policy decisions,
                  hash-chained audit entries, agent identities (<span className="font-mono">cond_agt_*</span>),
                  credentials in encrypted vault.
                </li>
                <li>
                  <span className="font-semibold text-stone-900">Not stored by default:</span> LLM
                  prompts, LLM responses, tool call payloads (metadata only).
                </li>
                <li>
                  <span className="font-semibold text-stone-900">In transit:</span> TLS 1.3 across
                  every surface.
                </li>
                <li>
                  <span className="font-semibold text-stone-900">At rest:</span> provider-managed
                  encryption (AES-256 across all sub-processors).
                </li>
                <li>
                  <span className="font-semibold text-stone-900">DPA:</span> available on request
                  for Business and Enterprise.
                </li>
              </ul>
            </div>

            {/* Sub-processors */}
            <div className="rounded-2xl border border-stone-200 bg-white p-6">
              <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-3">
                Sub-processors
              </p>
              <ul className="text-sm text-stone-600 space-y-1.5 leading-relaxed">
                <li><span className="font-semibold text-stone-900">Vercel</span> — web hosting</li>
                <li><span className="font-semibold text-stone-900">Render</span> — API + worker hosting</li>
                <li><span className="font-semibold text-stone-900">Clerk</span> — authentication and SSO</li>
                <li>Cloud-managed <span className="font-semibold text-stone-900">PostgreSQL</span> — primary data store</li>
                <li>Cloud-managed <span className="font-semibold text-stone-900">Redis</span> — queue and cache</li>
                <li>
                  Customer-chosen <span className="font-semibold text-stone-900">LLM providers</span>{" "}
                  (routed through Guard, not stored): Anthropic, OpenAI, Google, AWS Bedrock, Azure
                  OpenAI, Ollama, self-hosted.
                </li>
                <li className="text-stone-500 pt-1.5">
                  Full sub-processor list available on request.
                </li>
              </ul>
            </div>

            {/* SSO & access */}
            <div className="rounded-2xl border border-stone-200 bg-white p-6">
              <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-3">
                SSO &amp; access
              </p>
              <ul className="text-sm text-stone-600 space-y-2 leading-relaxed">
                <li>
                  <span className="font-semibold text-stone-900">Google, Microsoft, Okta</span> — OIDC,
                  shipped on Team and above.
                </li>
                <li>
                  <span className="font-semibold text-stone-900">SAML</span> — Enterprise, on request.
                </li>
                <li>
                  <span className="font-semibold text-stone-900">Role-based access control (RBAC)</span>{" "}
                  — per-user scoped permissions.
                </li>
                <li>
                  <span className="font-semibold text-stone-900">Session TTL</span> — configurable per
                  workspace.
                </li>
              </ul>
            </div>
          </div>

          <p className="text-xs text-stone-500 leading-relaxed">
            Need something not listed here — audit retention window, specific sub-processor names,
            SOC2 timeline, DPA text? Email{" "}
            <a href="mailto:security@conductai.ai" className="text-stone-900 font-semibold hover:underline">
              security@conductai.ai
            </a>
            . Answers within one business day.
          </p>
        </section>

        <section className="mb-16 border-t border-stone-100 pt-12">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Responsible disclosure</h2>
          <p className="text-stone-600 leading-relaxed">
            Found a security issue? Email <a href="mailto:security@conductai.ai" className="text-stone-900 font-semibold hover:underline">security@conductai.ai</a>. We aim to acknowledge within 24 hours and coordinate on disclosure timing.
          </p>
        </section>

        <section className="text-center border-t border-stone-100 pt-16">
          <Link
            href="/sign-up"
            className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
          >
            Start Discovery — 14 days free
          </Link>
        </section>
      </main>
    </div>
  )
}
