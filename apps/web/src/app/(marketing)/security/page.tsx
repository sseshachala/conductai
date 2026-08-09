import { CtaLink } from "@/components/marketing/CtaLink"

export default function SecurityPage() {
  return (
    <>
      <HeroSection />
      <LimitationsSection />
      <DisclosureSection />
    </>
  )
}

/* ─── Hero ──────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="max-w-3xl mx-auto px-6 pt-20 pb-10">
      <div className="inline-flex items-center gap-2 bg-amber-50 text-amber-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 inline-block" />
        Threat model
      </div>
      <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        What we do not protect (yet).
      </h1>
      <p className="text-lg text-stone-500 leading-relaxed mb-4">
        Guard enforces policies at the tool layer, across every AI agent your team runs. That scope is real and it compounds. There are also things it does not do today. This page names them directly, with our plan for each.
      </p>
      <p className="text-sm text-stone-400">Last reviewed: 2026-08-09</p>
    </section>
  )
}

/* ─── Limitations ────────────────────────────────────────────────────────── */

function LimitationsSection() {
  const items = [
    {
      title: "Credentials are decrypted in the executor process.",
      status: "Known gap",
      statusStyle: "bg-amber-100 text-amber-700",
      body: "When a workflow block runs, credentials stored in your workspace are decrypted in memory inside the executor process. A compromised executor with sufficient access could read them in plaintext. This is standard practice for secret injection into running processes — it is not unique to Conduct — but it is a real attack surface.",
      plan: "We are evaluating hardware-backed secret stores (AWS KMS envelope encryption, HashiCorp Vault dynamic secrets) that keep the plaintext window as short as possible and audit every decryption. The executor would receive a short-lived token, not the raw credential. Timeline: Q4 2026.",
    },
    {
      title: "No per-environment egress allowlist.",
      status: "Known gap",
      statusStyle: "bg-amber-100 text-amber-700",
      body: "Guard controls which tools an agent can call and enforces spend limits, but it does not currently restrict which network destinations a tool can reach. An agent with a Bash tool could make outbound requests to arbitrary endpoints — Guard will log the call but not block it based on destination.",
      plan: "Per-environment egress rules are on the Guard policy roadmap. The plan is to add a destination_allowlist field to the policy schema, evaluated at the proxy layer before any outbound call forwards. This requires the Guard Proxy to be in the path — a requirement we will document explicitly. Target: Q1 2027.",
    },
    {
      title: "No static analysis of third-party playbooks before install.",
      status: "Known gap",
      statusStyle: "bg-amber-100 text-amber-700",
      body: "Playbooks from the marketplace or imported via YAML are not statically analysed for dangerous patterns before install. A malicious playbook could contain a Bash block that exfiltrates data on first run. Guard policies apply at runtime, so the first execution is when enforcement kicks in — not before.",
      plan: "We are building a pre-install scanner that inspects block types, tool permissions, and shell commands against a deny-list before a playbook is activated. It will surface warnings in the install flow, not silently block. Community-contributed playbooks will require a manual review step before appearing in the public registry. Target: Q3 2026.",
    },
  ]

  return (
    <section className="max-w-3xl mx-auto px-6 py-10">
      <div className="space-y-10">
        {items.map((item) => (
          <div key={item.title} className="border border-stone-200 rounded-2xl p-8 bg-white">
            <div className="flex items-start justify-between gap-4 mb-5">
              <h2 className="text-lg font-bold text-stone-900 leading-snug">{item.title}</h2>
              <span className={`flex-shrink-0 text-xs font-semibold px-2.5 py-1 rounded-full ${item.statusStyle}`}>
                {item.status}
              </span>
            </div>
            <p className="text-stone-500 leading-relaxed mb-5">{item.body}</p>
            <div className="rounded-xl bg-stone-50 border border-stone-100 px-5 py-4">
              <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-2">Our plan</p>
              <p className="text-sm text-stone-600 leading-relaxed">{item.plan}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ─── Disclosure ─────────────────────────────────────────────────────────── */

function DisclosureSection() {
  return (
    <section className="bg-stone-50 border-t border-stone-200 px-6 py-16">
      <div className="max-w-3xl mx-auto">
        <div className="grid md:grid-cols-2 gap-10 items-start">
          <div>
            <h2 className="text-xl font-bold text-stone-900 mb-3">Report a vulnerability.</h2>
            <p className="text-stone-500 text-sm leading-relaxed mb-4">
              If you find a security issue in Guard, the API, or the CLI, disclose it to us before making it public. We will respond within 48 hours, confirm scope, and keep you informed through resolution.
            </p>
            <a
              href="mailto:security@conductai.ai"
              className="inline-flex items-center gap-2 text-sm font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
            >
              security@conductai.ai
            </a>
            <p className="text-xs text-stone-400 mt-3">
              We do not have a formal bug bounty programme yet. We will credit researchers by name if they wish.
            </p>
          </div>
          <div>
            <h2 className="text-xl font-bold text-stone-900 mb-3">What Guard does protect.</h2>
            <ul className="space-y-2 text-sm text-stone-600">
              {[
                "Tool-layer enforcement — block or warn before the agent acts",
                "Credential leak detection in prompts and tool inputs",
                "PII screening before calls reach LLM providers",
                "Spend limits enforced in real time per developer and workspace",
                "SHA-256 hash-chained audit log, tamper-evident and CISO-verifiable",
                "RFC 8693 token exchange for agent identity",
                "Fail-closed by default on API outage",
              ].map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <span className="text-emerald-500 font-bold mt-0.5">✓</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <div className="mt-6">
              <CtaLink className="rounded-lg bg-stone-900 text-white px-5 py-2.5 text-sm font-semibold hover:bg-stone-700 transition-colors" />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
