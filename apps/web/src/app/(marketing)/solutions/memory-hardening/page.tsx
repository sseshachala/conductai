import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Memory Hardening | Conduct",
  description:
    "Wire-level enforcement for OWASP ASI06 (Memory Poisoning) and MITRE ATLAS AML.M0031 (Memory Hardening). Guard governs the writes. In-process libraries secure the store. Together they cover the surface end to end.",
}

export default function MemoryHardeningPage() {
  return (
    <>
      <HeroSection />
      <ProblemSection />
      <LayerSplitSection />
      <RuleExamplesSection />
      <IntegrationSection />
      <CtaSection />
    </>
  )
}

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        For AppSec, ML security, and platform teams
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        Memory Poisoning is a shipped attack.{" "}
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">Guard the writes.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-3xl mx-auto leading-relaxed mb-6">
        Persistent agent memory is now a formal attack surface. OWASP ASI06 and MITRE ATLAS AML.M0031 name it directly.
        A poisoned document stored today shapes agent behavior across future users and tenants until someone notices.
        Guard sits between the agent and the memory tool, so poisoned content never becomes policy.
      </p>
      <p className="text-base text-stone-500 max-w-2xl mx-auto leading-relaxed italic mb-8">
        In-process libraries harden the store. Guard governs the writes. Same architecture as Okta plus Guard for identity.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a
          href="/registry?tab=compliance&pack=conduct-owasp"
          className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center"
        >
          Install the OWASP pack
        </a>
        <a
          href="https://cal.com/sudhi-seshachala-pks7pd"
          target="_blank"
          rel="noopener"
          className="rounded-xl border border-stone-300 bg-white text-stone-700 px-7 py-3.5 text-base font-semibold hover:border-stone-400 hover:shadow-sm transition-all w-full sm:w-auto text-center"
        >
          Book a walkthrough
        </a>
      </div>
    </section>
  )
}

const PROBLEMS = [
  {
    headline: "The payload is already inside.",
    body: "Prompt-level defenses catch the instruction at the door. Memory poisoning happens after the content is stored. Traditional input filtering does not see it.",
  },
  {
    headline: "One poisoned document becomes policy.",
    body: "A scraped doc, a user-supplied file, a tool output. Stored once, it steers agent behavior across sessions, users, and tenants for weeks.",
  },
  {
    headline: "Detection tools tell you after the fact.",
    body: "Post-hoc analysis flags weird outputs. It does not tell you which memory row caused them, or how to roll back. You need policy at the write, not analytics after the harm.",
  },
]

function ProblemSection() {
  return (
    <section className="bg-stone-50 border-y border-stone-200 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-center text-2xl font-black text-stone-900 tracking-tight mb-10">
          Why memory is the underrated attack surface.
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          {PROBLEMS.map((p) => (
            <div key={p.headline} className="border border-stone-200 rounded-xl bg-white p-6">
              <h3 className="text-sm font-bold text-stone-900 mb-2">{p.headline}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{p.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const LAYERS = [
  {
    role: "In-process memory library",
    covers: "Runs inside the agent process. Classifies content already in the store. Detects tampering. Provides rollback. Enforces cross-context isolation at the read path.",
    where: "The memory store itself.",
  },
  {
    role: "Conduct Guard",
    covers: "Sits at the wire, in front of every memory-write and memory-read tool call. Blocks or warns on writes that would introduce poison, promote untrusted content to durable tiers, or leak across tenant namespaces. Every decision lands in the hash-chained audit.",
    where: "The write path, before content reaches the store.",
  },
]

function LayerSplitSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-20">
      <div className="text-center mb-12">
        <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight mb-4">
          Two layers, one attack surface.
        </h2>
        <p className="text-stone-500 max-w-2xl mx-auto">
          Memory hardening is defense-in-depth. The library protects the store. Guard governs the writes. Neither alone
          covers OWASP ASI06 end to end.
        </p>
      </div>
      <div className="grid md:grid-cols-2 gap-5">
        {LAYERS.map((l) => (
          <div key={l.role} className="border border-stone-200 rounded-2xl p-6 bg-white">
            <p className="text-xs font-bold uppercase tracking-widest text-indigo-500 mb-2">{l.where}</p>
            <h3 className="text-lg font-bold text-stone-900 mb-3">{l.role}</h3>
            <p className="text-sm text-stone-600 leading-relaxed">{l.covers}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

const RULES = [
  {
    id: "asi06_memory_write_without_classification",
    label: "Warn",
    body: "Fires when an agent writes to persistent memory without a source or trust classification tag. Untagged content silently becomes policy across future sessions.",
  },
  {
    id: "asi06_untrusted_promotion_to_durable",
    label: "Block",
    body: "Fires when untrusted content (user input, scraped, tool output) is promoted to durable or long-term memory tiers without an explicit trust-promotion step.",
  },
  {
    id: "asi06_instruction_shaped_memory_write",
    label: "Block",
    body: "Fires when a memory write contains text that would act as a delayed instruction override on future recall.",
  },
  {
    id: "asi06_cross_tenant_memory_read",
    label: "Warn",
    body: "Fires on memory reads that span tenant or namespace boundaries. Cross-context reads leak one context poison into another.",
  },
  {
    id: "asi06_memory_integrity_bypass",
    label: "Warn",
    body: "Fires when writes to a trusted or verified tier omit an integrity claim (hash, signature, attestation).",
  },
]

function RuleExamplesSection() {
  return (
    <section className="bg-stone-950 px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-10">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-3">In the OWASP pack today</p>
          <h2 className="text-3xl font-black text-white tracking-tight mb-4">
            Five ASI06 rules ship in conduct-owasp v2.2.0.
          </h2>
          <p className="text-stone-400 max-w-2xl mx-auto text-sm leading-relaxed">
            Every rule is tagged with OWASP:ASI06 and MITRE_ATLAS:AML.M0031 for compliance evidence.
          </p>
        </div>
        <div className="space-y-3">
          {RULES.map((r) => (
            <div key={r.id} className="border border-stone-700 rounded-xl bg-stone-900 p-5 flex items-start gap-4">
              <span className={`px-2.5 py-1 rounded-lg text-xs font-bold uppercase tracking-wider flex-shrink-0 mt-0.5 ${r.label === "Block" ? "bg-red-500/20 text-red-300 border border-red-500/40" : "bg-amber-500/20 text-amber-300 border border-amber-500/40"}`}>
                {r.label}
              </span>
              <div>
                <p className="font-mono text-xs text-stone-500 mb-1">{r.id}</p>
                <p className="text-sm text-stone-300 leading-relaxed">{r.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function IntegrationSection() {
  return (
    <section className="max-w-4xl mx-auto px-6 py-20">
      <h2 className="text-center text-3xl font-black text-stone-900 tracking-tight mb-6">
        Reference architecture: Guard plus in-process memory hardening.
      </h2>
      <p className="text-center text-stone-500 max-w-2xl mx-auto mb-10">
        Wire the two layers together for end-to-end coverage of OWASP ASI06 and MITRE ATLAS AML.M0031.
      </p>
      <div className="border border-stone-200 rounded-xl p-6 bg-stone-50 mb-6">
        <ol className="space-y-4 text-sm text-stone-700 leading-relaxed">
          <li>
            <span className="font-bold text-stone-900">1. Agent invokes a memory-write tool.</span>{" "}
            memory_save, vector_store_add, mcp__*memory*, or any tool matching the memory naming pattern.
          </li>
          <li>
            <span className="font-bold text-stone-900">2. Guard proxy or hook evaluates the call.</span>{" "}
            OWASP ASI06 rules check for classification tags, untrusted-promotion attempts, instruction-shaped content,
            cross-tenant scope, and integrity claims. Allow, warn, or block returns before the tool executes.
          </li>
          <li>
            <span className="font-bold text-stone-900">3. Allowed writes reach the in-process library.</span>{" "}
            An in-process memory-hardening library applies in-store classification, cross-context isolation, and
            integrity tracking.
          </li>
          <li>
            <span className="font-bold text-stone-900">4. Both layers write to the same audit chain.</span>{" "}
            Guard decisions plus in-process events feed one hash-chained record. Auditors query one table, not two.
          </li>
          <li>
            <span className="font-bold text-stone-900">5. Rollback is a first-class action.</span>{" "}
            When the library detects tampering, it triggers a rollback and Guard records the event with lineage back to
            the write that caused it.
          </li>
        </ol>
      </div>
      <p className="text-xs text-stone-500 italic text-center">
        Compatible with any memory-hardening library that implements the ASI06 primitives (classification, promotion
        controls, isolation, integrity). The OWASP Agent Memory Guard project is the reference implementation named by
        MITRE ATLAS AML.M0031.
      </p>
    </section>
  )
}

function CtaSection() {
  return (
    <section className="px-6 py-24 bg-gradient-to-br from-indigo-600 to-violet-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          Cover OWASP ASI06 at the wire today.
        </h2>
        <p className="text-indigo-100 text-lg mb-8">
          Install the OWASP pack, get five ASI06 rules mapped to MITRE ATLAS AML.M0031. Pair with your memory-hardening
          library for end-to-end coverage.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="/registry?tab=compliance&pack=conduct-owasp"
            className="rounded-xl bg-white text-indigo-600 px-8 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center"
          >
            Install the OWASP pack
          </a>
          <a
            href="/use-cases#content-inspection"
            className="rounded-xl border border-white/40 text-white px-8 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center"
          >
            Read the deep dive
          </a>
        </div>
      </div>
    </section>
  )
}
