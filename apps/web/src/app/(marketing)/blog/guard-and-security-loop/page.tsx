import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Conduct is Guard: the all-in-one AI compliance and security platform. | Conduct",
  description:
    "One platform, one control plane, one audit trail. Guard governs every AI call, closes every security finding, and produces the compliance evidence in the same table.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Positioning
          </span>
          <span className="text-xs text-stone-400">July 25, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          Conduct is Guard: the all-in-one AI compliance and security platform.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          One platform. One control plane for every AI call, every security
          finding, every fix, every audit line. Guard is the wire, Guard is
          the loop, Guard is the evidence. Everything Conduct ships lives
          under one compliance and security surface.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The problem with breadth</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Over the last quarter Conduct shipped 36 playbooks. PR reviewers,
          release notes generators, incident responders, dependency updaters,
          docs drift detectors, flaky test triage, third-party autopilot fix,
          bulk PR reviewers, terraform reviewers. All useful. All shipped. All
          in the registry, all working today.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          But if you asked five people what Conduct <em>is</em>, you got five
          answers. Governance platform. Playbook framework. Security loop. AI
          cost control. Compliance evidence engine. Every answer was partially
          right, which meant every buyer had to work out for themselves which
          part applied to them. That&apos;s a bad demo, and it&apos;s a slow deal.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          So we&apos;re collapsing the pitch surface into one thing. Guard.
          The all-in-one AI compliance and security platform.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">One platform — Guard</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Guard sits synchronously on every AI call your engineers make. Claude
          Code, Cursor, Copilot, Windsurf, ChatGPT desktop, Claude desktop,
          Codex. Any LLM API call routed through the Guard proxy. Every MCP
          tool call. Every playbook block that talks to a model.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          For each call, the policy engine returns allow, warn, or block before
          the call proceeds. Fail closed. Hash-chained audit trail. The
          governance decision is a first-class artifact, not a log line.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          Guard answers a specific question a CISO gets asked by their board:{" "}
          <em>what is the AI in our environment actually allowed to do, and
          where is the proof?</em>
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The security loop is part of Guard</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Guard catches things at the wire. The same platform catches things in
          the code. Scanner runs, threat model runs, third-party audit runs, all
          file into one findings table inside Guard. Findings above a threshold
          chain into an autopilot-fix playbook that drafts the mitigation PR. A
          human approves. A metric moves. Same identity, same audit chain, same
          dashboard.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          The loop is what turns a scanner from a checklist into an outcome —
          and because it&apos;s the same platform as the wire-level control,
          it&apos;s also the compliance artifact. Every call, every finding,
          every fix, every approval is one hash-chained entry. SOC 2 CC7.3,
          PCI DSS 12.3.1, ISO 27001 A.14.2.1, the EU AI Act — all point at the
          same table.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Everything else runs on Guard</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          The PR reviewer playbook still ships. The release-notes generator
          still ships. Incident responder, dependency updater, docs drift,
          flaky test, all still ship. Installable from the registry,
          documented, supported, on the roadmap.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          They all run under Guard&apos;s policy, spend, and audit envelope.
          Every playbook call is a Guard call. Every fix is a Guard-signed
          artifact. There is no second product — the registry is Guard&apos;s
          workload catalog.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Why this is the right cut</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Autopilot-for-general-dev is a crowded market. Cursor, Copilot Workspace,
          Devin, Cognition, GitHub Agent HQ — a lot of well-funded companies
          fighting for it. We can&apos;t win on breadth there, and we shouldn&apos;t try.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          Compliance and security outcomes are measurable. MTTR, findings fixed
          per week, blocks per day, compliance evidence per audit, spend under
          policy. One platform for all of them collapses tool sprawl in the
          exact place a CISO is being asked to justify AI adoption.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          Guard is a control. Guard is the evidence. Guard is the remediation
          loop. All three are things CISOs already know how to buy. We&apos;re
          not inventing a new category — we&apos;re taking the AI compliance
          and security stack that&apos;s stuck across five tools and putting
          it on one shelf.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What this changes for you</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          If you already use Conduct: nothing about the code. Every playbook
          you installed still works. Your Guard rules still enforce. Your loop
          still runs. It&apos;s all Guard now, in name and in surface. The
          website will get simpler. The demo will get shorter.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          If you&apos;re evaluating: the pitch is now short enough to fit on one
          screen. One platform for AI compliance and security. Wire-level
          governance, closed-loop remediation, hash-chained evidence.
          Fifteen-minute demo, three questions, a decision either way.
        </p>

        <div className="mt-12 border-t border-stone-100 pt-8">
          <CtaLink className="rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors" />
        </div>

      </div>
    </article>
  )
}
