export const metadata = {
  title: "NeMo Guardrails + Conduct: app safety layer + org governance layer | Conduct",
  description:
    "NeMo Guardrails makes each app safe. Conduct makes the fleet governable. One rule spanning every NeMo app, one audit chain, one kill switch, one spend cap. Reference architecture.",
}

export default function NemoGuardrailsPage() {
  return (
    <>
      <HeroSection />
      <TwoLayersSection />
      <FleetSection />
      <PluginSection />
      <ActivityLinkSection />
      <CtaSection />
    </>
  )
}

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        Reference architecture · NVIDIA NeMo Guardrails + Conduct
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        NeMo makes each app safe.{" "}
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">
          Conduct makes the fleet governable.
        </span>
      </h1>
      <p className="text-xl text-stone-500 max-w-3xl mx-auto leading-relaxed mb-6">
        Five teams pick NeMo Guardrails for their five agents. Each writes its own <code className="text-base bg-stone-100 px-1.5 py-0.5 rounded">config.yml</code>.
        Now IT wants one rule across all five, one audit chain, one kill switch, one spend cap.
        NeMo doesn&apos;t try to solve that — it&apos;s a different layer. Conduct does.
      </p>
      <p className="text-base text-stone-500 max-w-2xl mx-auto leading-relaxed italic mb-8">
        Your app safety layer keeps each conversation on-policy. The governance layer keeps
        the fleet on-policy.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a
          href="https://cal.com/sudhi-seshachala-pks7pd"
          target="_blank"
          rel="noopener"
          className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center"
        >
          Book a reference walkthrough
        </a>
        <a
          href="https://pypi.org/project/conduct-nemo-guard/"
          target="_blank"
          rel="noopener"
          className="rounded-xl border border-stone-300 bg-white text-stone-900 px-7 py-3.5 text-base font-semibold hover:border-stone-500 transition-colors w-full sm:w-auto text-center"
        >
          pip install conduct-nemo-guard
        </a>
      </div>
    </section>
  )
}

/* ─── Two Layers ───────────────────────────────────────────────────────── */

function TwoLayersSection() {
  return (
    <section className="py-20 px-6 bg-white border-t border-stone-100">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">
            Two layers, one stack
          </p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight">
            App safety and org governance<br />are different problems.
          </h2>
        </div>
        <div className="grid md:grid-cols-2 gap-6">
          <div className="rounded-2xl border border-stone-200 bg-stone-50 p-8">
            <div className="text-2xl mb-3">🛟</div>
            <h3 className="text-lg font-bold text-stone-900 mb-3">App safety layer — NeMo Guardrails</h3>
            <p className="text-sm text-stone-600 leading-relaxed mb-4">
              Keeps one application&apos;s conversation on-policy. Runs inside the app process,
              defined per app, evaluated per turn.
            </p>
            <ul className="text-sm text-stone-700 space-y-2">
              <li>· Colang DSL for rails</li>
              <li>· LLM-based moderation, jailbreak detection</li>
              <li>· Streaming rail evaluation</li>
              <li>· Multimodal (image, audio) safety</li>
              <li>· 20+ third-party detector integrations</li>
            </ul>
          </div>
          <div className="rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-violet-50 p-8">
            <div className="text-2xl mb-3">🏛️</div>
            <h3 className="text-lg font-bold text-stone-900 mb-3">Governance layer — Conduct</h3>
            <p className="text-sm text-stone-600 leading-relaxed mb-4">
              Keeps the whole fleet on-policy. Sits above every app, every LLM, every agent,
              every tool call. One rule catalog, one audit chain, one console.
            </p>
            <ul className="text-sm text-stone-700 space-y-2">
              <li>· Workspace-wide rules across every agent</li>
              <li>· Hash-chained tamper-evident audit</li>
              <li>· HITL approval workflow with Slack + resume tokens</li>
              <li>· Agent identity (<code className="text-xs bg-white px-1.5 py-0.5 rounded">cond_agt_*</code>) scoping blast radius</li>
              <li>· Spend caps + budget alerts</li>
              <li>· 8 compliance packs (SOC 2, HIPAA, PCI, EU AI Act, NIST AI RMF, ISO 42001, IRS 1075, OWASP)</li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Fleet Scenario ───────────────────────────────────────────────────── */

function FleetSection() {
  return (
    <section className="py-20 px-6 bg-stone-50 border-t border-stone-100">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">
            The fleet problem
          </p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight">
            Five apps. Five configs.<br />One org.
          </h2>
        </div>
        <p className="text-lg text-stone-600 max-w-3xl mx-auto leading-relaxed mb-8 text-center">
          Every team picks the right rails for their app. Good. Now the CISO asks:
        </p>
        <div className="grid md:grid-cols-2 gap-4">
          {[
            { q: "How do I block all PII across every agent without editing 5 configs?", a: "One workspace rule. Applies to every NeMo app that calls Conduct." },
            { q: "Where do I query every rail decision across all 5 apps for the SOC 2 auditor?", a: "One audit surface. Filter by source, decision, rule, date, developer." },
            { q: "Can I pause all agent activity across the fleet if something goes wrong?", a: "One kill switch. Every downstream agent respects the workspace policy." },
            { q: "How do I cap total spend across the fleet, not per app?", a: "One workspace budget. Enforced at the proxy layer regardless of framework." },
            { q: "When an audit finding lands, can I prove which agents ran what?", a: "Hash-chained ledger with agent identity. Every entry attributes to a cond_agt_* token." },
            { q: "How do I ship SOC 2 / EU AI Act evidence from this fleet?", a: "Compliance packs export controls-mapped evidence directly from the audit chain." },
          ].map((qa, i) => (
            <div key={i} className="rounded-2xl bg-white border border-stone-200 p-6">
              <p className="text-sm font-bold text-stone-900 mb-2 leading-snug">Q: {qa.q}</p>
              <p className="text-sm text-stone-500 leading-relaxed">A: {qa.a}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Plugin ───────────────────────────────────────────────────────────── */

function PluginSection() {
  return (
    <section className="py-20 px-6 bg-white border-t border-stone-100">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-10">
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">
            Wire it up
          </p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight">
            One Colang input rail.<br />Every NeMo app becomes fleet-governable.
          </h2>
        </div>
        <p className="text-base text-stone-500 max-w-2xl mx-auto leading-relaxed mb-8 text-center">
          The <code className="text-sm bg-stone-100 px-1.5 py-0.5 rounded">conduct-nemo-guard</code> plugin
          exposes a Colang action that hits Conduct on every user turn. Blocked verdicts short-circuit before
          the LLM runs. Every decision lands in the workspace audit chain, source-tagged <code className="text-sm bg-stone-100 px-1.5 py-0.5 rounded">nemo</code>.
        </p>
        <div className="rounded-2xl bg-stone-900 text-stone-100 p-6 font-mono text-xs leading-relaxed overflow-x-auto">
          <div className="text-stone-400"># config.yml</div>
          <div>rails:</div>
          <div>{"  "}input:</div>
          <div>{"    "}flows:</div>
          <div>{"      "}- check_policy</div>
          <br />
          <div className="text-stone-400"># rails.co</div>
          <div>define flow check_policy</div>
          <div>{"  "}$verdict = execute conduct_guard_verdict(</div>
          <div>{"    "}tool_name=&quot;support_bot_message&quot;,</div>
          <div>{"    "}prompt=$user_message</div>
          <div>{"  "})</div>
          <div>{"  "}if $verdict == &quot;block&quot;</div>
          <div>{"    "}bot inform_policy_block</div>
          <div>{"    "}stop</div>
        </div>
        <p className="text-sm text-stone-500 max-w-2xl mx-auto leading-relaxed mt-6 text-center">
          Full runnable example: <a href="https://github.com/sseshachala/conductai/tree/main/packages/conduct-nemo-guard" className="text-indigo-600 hover:text-indigo-800 font-semibold" target="_blank" rel="noopener">packages/conduct-nemo-guard</a> in the repo.
        </p>
      </div>
    </section>
  )
}

/* ─── Activity Link ────────────────────────────────────────────────────── */

function ActivityLinkSection() {
  return (
    <section className="py-16 px-6 bg-gradient-to-br from-indigo-50 via-white to-violet-50 border-y border-indigo-100">
      <div className="max-w-3xl mx-auto text-center">
        <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600 mb-3">
          Observability
        </p>
        <h2 className="text-2xl sm:text-3xl font-bold text-stone-900 tracking-tight mb-4">
          See every NeMo rail decision in one view.
        </h2>
        <p className="text-base text-stone-600 max-w-xl mx-auto leading-relaxed mb-6">
          Guard Activity filters by source. Pick <code className="text-sm bg-white border border-stone-200 px-1.5 py-0.5 rounded">nemo</code> in the tool
          filter (or use the deep link below) to see every rail decision from every NeMo app in your workspace.
        </p>
        <a
          href="/logs/guard?ai_tool=nemo"
          className="inline-flex rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-bold hover:bg-stone-700 transition-colors"
        >
          Open Guard Activity — NeMo only →
        </a>
      </div>
    </section>
  )
}

/* ─── CTA ──────────────────────────────────────────────────────────────── */

function CtaSection() {
  return (
    <section className="py-20 px-6 bg-white border-t border-stone-100">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight mb-4">
          Already running NeMo in production?
        </h2>
        <p className="text-lg text-stone-500 max-w-xl mx-auto leading-relaxed mb-8">
          We&apos;re hiring two design partners this quarter — teams that already ship NeMo apps
          and need the governance layer above them. 30-min scoping call.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="https://cal.com/sudhi-seshachala-pks7pd"
            target="_blank"
            rel="noopener"
            className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors"
          >
            Book a design-partner call
          </a>
          <a
            href="tel:+18325288110"
            className="rounded-xl border border-stone-300 bg-white text-stone-900 px-7 py-3.5 text-base font-semibold hover:border-stone-500 transition-colors"
          >
            Or call direct: (832) 528-8110
          </a>
        </div>
      </div>
    </section>
  )
}
