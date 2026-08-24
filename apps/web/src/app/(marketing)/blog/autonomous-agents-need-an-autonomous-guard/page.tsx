import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Autonomous agents need an autonomous guard | Conduct",
  description:
    "A self-driving network agent detects a BGP flap and proposes a fix. Before that change reaches production, ConductGuard intercepts it, asks a human, records the decision. Watch the 90-second demo.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Autonomy
          </span>
          <span className="text-xs text-stone-400">August 23, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          Autonomous agents need an autonomous guard.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          An AI agent detects a BGP flap across two fabrics, correlates the
          incident, and proposes a remediation. Before that change reaches
          production, ConductGuard steps in.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">

        <div className="aspect-video mb-12">
          <iframe
            className="w-full h-full rounded-2xl border border-stone-200"
            src="https://www.youtube.com/embed/NdgfQRkSg14"
            title="Self-Driving Network — HITL demo with ConductGuard"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
          />
        </div>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The scenario</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Autonomous AI agents can detect and remediate network problems faster
          than humans. That is not the interesting part anymore. The
          interesting part is what happens when the proposed fix is wrong.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          In this 90-second demo we walk through a real-world autonomous
          networking scenario: a BGP session flap on a Juniper Mist core, a
          DFS event on an Aruba Central campus fabric, one agent watching
          both. The agent correlates the anomalies, produces a synchronized
          remediation plan, and moves to push a config change to production.
          That is the moment ConductGuard intercepts.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What the guard does at runtime</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Conduct AI provides a runtime governance layer for autonomous and
          agentic systems. Six things happen on every sensitive action, in the
          order they matter:
        </p>
        <ol className="list-decimal list-inside text-stone-700 leading-relaxed mb-6 space-y-2">
          <li>
            <strong>Intercept</strong> high-risk agent actions before
            execution. The agent&apos;s intent is inspected at the runtime
            layer, not after the fact in a log.
          </li>
          <li>
            <strong>Enforce policy</strong> as declarative YAML, evaluated on
            every request. One rule per intent, version-controlled, signed
            when it changes.
          </li>
          <li>
            <strong>Require human approval</strong> for sensitive production
            changes. The run pauses. Nothing executes until a human decides.
          </li>
          <li>
            <strong>Trigger Slack alerts</strong> with full context.
            One-click Approve or Reject. The message carries the workflow,
            the run link, the requester, the rule that fired.
          </li>
          <li>
            <strong>Track every agent action</strong>, policy decision, and
            tool call in a hash-chained ledger. Tampering with one row
            invalidates the chain.
          </li>
          <li>
            <strong>Govern behavior</strong> using frameworks such as OWASP
            Agentic AI security guidance, SOC 2 CC6, HIPAA §164.312, EU AI
            Act Article 15. Compliance packs map policy to real clauses.
          </li>
        </ol>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Why this is not a brake</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          The goal is not to stop autonomous infrastructure. It is to make
          autonomy safe enough for production.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          As enterprises move toward self-driving networks, autonomous
          remediation, and AI-operated infrastructure, agents need more than
          intelligence. They need identity, policy enforcement, observability,
          auditability, and clear boundaries around what they are allowed to
          do.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          The remediation logic stays with the agent. The decision to touch
          production stays with a human. The record of both stays in the
          ledger.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What runs in the demo</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          One YAML playbook. Three blocks: assess, deploy, report. Guard sits
          between them with a single approve-prod-deploy rule.
        </p>
        <ul className="list-disc list-inside text-stone-700 leading-relaxed mb-4 space-y-1">
          <li>Agent proposes multi-fabric prod push.</li>
          <li>Guard matches the command against policy.</li>
          <li>Slack Approve / Reject buttons post to the on-call channel.</li>
          <li>One click resumes the run or halts it.</li>
          <li>Hash-chained audit records the decider, timestamp, and reason.</li>
        </ul>
        <p className="text-stone-700 leading-relaxed mb-6">
          Same pattern works for a database migration, a bulk email, a cloud
          IAM change, or an outbound API call. The rule changes; the runtime
          shape does not.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Getting started</h2>
        <pre className="bg-stone-900 text-stone-100 text-sm rounded-lg p-4 overflow-x-auto mb-6"><code>{`pip install conduct-cli
conduct login
conduct install self_driving_network_approval_demo
conduct run "Self-Driving Network — Prod Config Push (HITL)"`}</code></pre>

        <p className="text-stone-700 leading-relaxed mb-6">
          Autonomous agents need an autonomous guard.
        </p>

        <div className="mt-12 border-t border-stone-100 pt-8">
          <CtaLink className="rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors" />
        </div>

      </div>
    </article>
  )
}
