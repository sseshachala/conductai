import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Threat modeling is a playbook, not a product. | Conduct",
  description:
    "Threat modeling has been treated as a workshop, a tool category, a compliance checkbox. It's none of those things. It's a task the AI in your PR flow can do on every merge. Here's how we shipped it as one YAML file.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-red-700 bg-red-50 border border-red-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Security
          </span>
          <span className="text-xs text-stone-400">July 25, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          Threat modeling is a playbook, not a product.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          The security industry has spent twenty years selling threat modeling as a
          workshop, a tool category, a compliance checkbox. It&apos;s none of those things.
          It&apos;s a task the AI already in your PR flow can do on every merge. We just
          shipped it as one YAML file.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The workshop that dies in a drawer</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Every regulated org has done threat modeling at least once. Someone booked
          two days on the calendar, a security architect ran STRIDE on a whiteboard,
          the output landed in a PDF. Six months later the architecture drifted, three
          services got added, two APIs got refactored, and the threat model was fiction.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          Auditors still asked for it. So most teams either produced the stale PDF, or
          ran the workshop again the week before the audit. Neither is governance.
          Both are theater.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What threat modeling actually is</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Threat modeling is the reasoning step where you look at a design and ask,
          for each STRIDE category: what could go wrong here? Spoofing, Tampering,
          Repudiation, Information disclosure, Denial of service, Elevation of privilege.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          Vulnerability scanners can&apos;t do this. A scanner reads code and matches known
          bad patterns. It has no concept of what the code is trying to do, or what
          would be catastrophic if it did the wrong thing. It can find the string
          <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">eval()</code>. It
          cannot tell you that your new endpoint accepts a <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">userId</code>{" "}
          query parameter and returns billing data without checking ownership.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          The reasoning is the hard part. And it&apos;s exactly what the current class of
          AI models is good at.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">How we shipped it</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          One YAML file: <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">apps/api/playbooks/threat-modeler.yaml</code>.
          It hooks into the existing Conduct runtime. No new module, no new database
          table, no new UI page. Six blocks:
        </p>
        <ol className="list-decimal pl-6 text-stone-700 leading-relaxed mb-6 space-y-1">
          <li><strong>recall_prior</strong> — read the last threat model for this repo</li>
          <li><strong>plan</strong> — single turn: identify what changed in the PR and which STRIDE categories are in scope</li>
          <li><strong>draft_stride</strong> — agentic turn: enumerate concrete threats tied to specific code paths</li>
          <li><strong>file_findings</strong> — POST each threat to <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">/security-findings</code></li>
          <li><strong>comment_pr</strong> — post the markdown threat model as a PR comment</li>
          <li><strong>record</strong> — save the threat model so the next PR can skip duplicates</li>
        </ol>
        <p className="text-stone-700 leading-relaxed mb-6">
          Findings flow into the same table as scanner output. They show up in the
          same <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">/secure/findings</code>{" "}
          UI. They roll into the same MTTR metrics. If severity is high, they chain
          into <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">security-autopilot-fix</code>{" "}
          which drafts a PR with the mitigation. Full loop, no glue code.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Why this is not a product</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          CognitivTrust, IriusRisk, ThreatModeler, and a handful of newer entrants
          are selling threat modeling as a dedicated product with its own dashboard,
          its own workflow, its own login. The pitch is legitimate. The design is
          wrong for how modern teams actually work.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          Threat modeling is not a separate activity from the rest of security. It
          is one participant in the loop that already includes scanning, remediation,
          and audit. Splitting it into its own tool is the same category error as
          splitting <em>dependency scanning</em> into a separate product from{" "}
          <em>SAST</em> — which is why Snyk, Semgrep, and every SCA vendor eventually
          converged into ASPM platforms.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          If the AI in your PR flow can draft a threat model as easily as it can
          suggest a variable rename, it should. And the output should land in the
          same place every other security finding lands.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What it costs</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          One playbook run per PR. Sonnet 4.6 is enough — STRIDE is structured
          output, not reasoning at the edge of the model. In our own repo, a run
          takes 30-60 seconds and costs under 5 cents. Compliance evidence for
          SOC 2 CC7.3, PCI DSS 12.3.1, and ISO 27001 A.14.2.1 falls out for free.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          If you want threat modeling that stays current, isn&apos;t a separate
          product, and files into your existing security loop, the playbook is in
          the registry under <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">threat-modeler</code>.
          Install it, point it at a repo, watch STRIDE run on your next PR.
        </p>

        <div className="mt-12 border-t border-stone-100 pt-8">
          <CtaLink className="rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors" />
        </div>

      </div>
    </article>
  )
}
