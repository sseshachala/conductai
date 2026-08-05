import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Action Governance for business agents | Conduct",
  description:
    "Capability is not authority. Guard sits between your agent and its action tools, checking every refund, cancellation, account update, and commitment against the current policy before the action runs.",
}

export default function ActionGovernancePage() {
  return (
    <>
      <HeroSection />
      <ProblemSection />
      <HowItWorksSection />
      <PolicyExampleSection />
      <MetricsSection />
      <CtaSection />
    </>
  )
}

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        For CX, ops, and platform teams shipping business agents
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        Capability is not{" "}
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">authority.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-8">
        An agent that answers questions is a search box with a hallucination risk. An agent that issues
        refunds is a financial actor with the same risk. Guard sits between the agent and the action tool
        so the answer to &ldquo;can I do this&rdquo; is decided by policy, not by prompt.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a
          href="/docs#action-tools"
          className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center"
        >
          See the policy pattern
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

const CASES = [
  {
    headline: "Air Canada.",
    body: "A chatbot invented a bereavement fare policy. The tribunal ordered the airline to honor it. The agent had authority to commit the company. Nobody had put a policy in front of the commitment.",
  },
  {
    headline: "Klarna.",
    body: "A rules change misfired inside an automated CX flow. Thousands of decisions had to be reversed after the fact. The blast radius was measured in customer relationships, not tickets.",
  },
  {
    headline: "Your next incident.",
    body: "An agent will offer a refund larger than the disputed amount. An agent will cancel a subscription for the wrong reason code. An agent will commit a price it should not commit. The mistake will look reasonable in the transcript.",
  },
]

function ProblemSection() {
  return (
    <section className="bg-stone-50 border-y border-stone-200 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-center text-2xl font-black text-stone-900 tracking-tight mb-10">
          Agents that take real actions leave real receipts.
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          {CASES.map((c) => (
            <div key={c.headline} className="border border-stone-200 rounded-xl bg-white p-6">
              <h3 className="text-sm font-bold text-stone-900 mb-2">{c.headline}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{c.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const STEPS = [
  {
    n: "01",
    title: "The agent calls an action tool.",
    body: "issue_refund, cancel_subscription, update_account, send_email, apply_credit. Any tool that produces a real-world outcome.",
  },
  {
    n: "02",
    title: "Guard checks the call against the current policy.",
    body: "Is this refund inside the allowed amount for the agent role. Is the cancellation reason on the allowed list. Does the commitment need a supervisor.",
  },
  {
    n: "03",
    title: "Allow, warn, or block.",
    body: "Allow runs the tool. Warn hands off to a human. Block returns a clean refusal the agent can explain to the customer in language.",
  },
  {
    n: "04",
    title: "One audit line, hash-chained.",
    body: "Customer, amount, reason, reviewer, and the specific rule that fired. Finance sees the audit line, not the mistake.",
  },
]

function HowItWorksSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-20">
      <div className="text-center mb-12">
        <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight mb-4">
          Policy in front of every action.
        </h2>
        <p className="text-stone-500 max-w-2xl mx-auto">
          Guard treats action calls the way a payment processor treats card auths. Every call goes through
          policy before the outcome commits.
        </p>
      </div>
      <div className="space-y-4">
        {STEPS.map((s) => (
          <div key={s.n} className="border border-stone-200 rounded-xl p-6 bg-white flex gap-5">
            <span className="text-xs font-mono text-stone-400 flex-shrink-0 mt-1">{s.n}</span>
            <div>
              <h3 className="text-base font-bold text-stone-900 mb-1.5">{s.title}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{s.body}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function PolicyExampleSection() {
  return (
    <section className="bg-stone-950 px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-3 text-center">A real policy, in YAML</p>
          <h2 className="text-center text-3xl font-black text-white tracking-tight mb-4">
            The refund-cap rule.
          </h2>
          <p className="text-stone-400 text-center max-w-2xl mx-auto text-sm leading-relaxed">
            Declarative. Ship without a deploy. This rule blocks refunds above a hard cap and requires
            supervisor review for anything more than twice the disputed amount.
          </p>
        </div>
        <div className="border border-stone-700 rounded-xl bg-stone-900 p-6 overflow-x-auto">
          <pre className="text-sm text-stone-200 font-mono leading-relaxed">
{`# ~/.conductguard/policies/refund-cap.yaml
name: refund-cap
applies_to:
  - "tool:issue_refund"
rules:
  - id: block-over-1000
    when:
      arg.amount_usd: { gt: 1000 }
    action: block
    reason: "Refund exceeds hard cap. Route to finance."

  - id: warn-over-2x-dispute
    when:
      arg.amount_usd: { gt: "\${arg.disputed_amount_usd} * 2" }
    action: warn
    handoff: supervisor
    reason: "Refund is more than twice the disputed amount. Supervisor review required."`}
          </pre>
        </div>
        <p className="text-stone-500 text-sm mt-6 text-center">
          The same pattern applies to any action tool. Cancellations, pricing commitments, DB writes,
          outbound sends. The rule grammar is the same.
        </p>
      </div>
    </section>
  )
}

const METRICS = [
  { k: "Actions above threshold", v: "How often the agent tried something big enough to matter." },
  { k: "Human handoffs per week", v: "The volume routed to a person. Guides staffing and threshold tuning." },
  { k: "Out-of-policy attempts", v: "Blocks that would have been mistakes. Your best signal that the policy is real." },
  { k: "Median handoff time", v: "The customer wait cost. Tune your escalation SLA against this." },
]

function MetricsSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-20">
      <h2 className="text-center text-3xl font-black text-stone-900 tracking-tight mb-10">
        Metrics that move once policy is in front.
      </h2>
      <div className="grid sm:grid-cols-2 gap-5">
        {METRICS.map((m) => (
          <div key={m.k} className="border border-stone-200 rounded-xl p-6 bg-white">
            <h3 className="text-sm font-bold text-stone-900 mb-2">{m.k}</h3>
            <p className="text-sm text-stone-500 leading-relaxed">{m.v}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

function CtaSection() {
  return (
    <section className="px-6 py-24 bg-gradient-to-br from-indigo-600 to-violet-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          Give your agents authority they can prove.
        </h2>
        <p className="text-indigo-100 text-lg mb-8">
          Guard’s policy engine is the same one that runs on your model calls today. Gating an action
          tool is one YAML rule, not a new integration.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="/docs#action-tools"
            className="rounded-xl bg-white text-indigo-600 px-8 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center"
          >
            See the policy pattern
          </a>
          <a
            href="/use-cases#action-governance"
            className="rounded-xl border border-white/40 text-white px-8 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center"
          >
            Read the deep dive
          </a>
        </div>
      </div>
    </section>
  )
}
