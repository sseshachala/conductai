import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "The MCP enterprise spec ships July 28. The implementation problem is yours. | Conduct",
  description:
    "Anthropic fixed the protocol. Enforcement, tool integrity, and audit evidence are now implementation problems — and every vendor will race to solve them.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Security
          </span>
          <span className="text-xs text-stone-400">July 28, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          The MCP enterprise spec ships today. The implementation problem is yours.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          Anthropic fixed the protocol. That moves the security problem downstream —
          to enforcement, tool integrity, and audit evidence. Every governance vendor
          will race to solve this. None of them have fully solved it yet.
        </p>
      </div>

      <hr className="border-stone-100 mb-10" />

      <div className="prose prose-stone prose-sm max-w-none space-y-8 text-stone-700 leading-relaxed">

        <section>
          <h2 className="text-xl font-bold text-stone-900 mb-3">What the spec fixes</h2>
          <p>
            The MCP 2024-11-05 enterprise release addresses three real protocol problems.
            Stateless transport is gone. The handshake is replaced. Authorization
            is re-aligned with OAuth 2.1.
          </p>
          <p className="mt-4">
            Session hijacking, as a protocol risk, is largely designed out.
            This is good engineering. It is also the beginning of a different problem,
            not the end of the security problem.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-bold text-stone-900 mb-3">What shifts to you</h2>
          <p>
            Akamai, analyzing the release candidate, wrote that the changes
            &ldquo;fundamentally reshape where security responsibilities reside.&rdquo;
          </p>
          <p className="mt-4">
            Away from the protocol, toward the implementation layer. In the current
            ecosystem, 36.7 percent of 7,000 analyzed MCP servers are potentially
            vulnerable to SSRF. The NSA has issued formal hardening guidance.
            A secure protocol running on insecure implementations is not a secure system.
          </p>
          <p className="mt-4">
            A tool call is not a message. It is an action — a payment, a database
            write, a record changed. The moment an agent takes actions in a regulated
            process, this becomes a compliance obligation, not a security discussion.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-bold text-stone-900 mb-3">The five things the spec expects you to own</h2>
          <p>
            Enterprise MCP governance requires five implementation-layer controls.
            The spec defines the handshake. It defines none of these.
          </p>
          <p className="mt-4 text-stone-500 text-sm">
            Multiple vendors — including those with access to Claude Code — will
            build these. The question is not whether someone will build them. It is
            whether you will have them in production before your next compliance review.
          </p>

          <div className="mt-6 space-y-6">
            <div className="border-l-4 border-indigo-500 pl-5">
              <h3 className="font-bold text-stone-900 mb-1">01 — Inventory</h3>
              <p className="text-sm">
                Know every MCP server running in your organization. Which tools are
                registered. Which are active. Which are shadow deployments nobody
                approved. You cannot govern what you cannot see.
              </p>
            </div>

            <div className="border-l-4 border-indigo-500 pl-5">
              <h3 className="font-bold text-stone-900 mb-1">02 — Identity</h3>
              <p className="text-sm">
                Know who — and what — is calling each tool. OAuth 2.1 establishes
                the handshake identity. It does not establish which developer, which
                agent, which workflow triggered the call. That granularity requires
                instrumentation at the hook or proxy layer.
              </p>
            </div>

            <div className="border-l-4 border-indigo-500 pl-5">
              <h3 className="font-bold text-stone-900 mb-1">03 — Policy</h3>
              <p className="text-sm">
                Define what tools and actions are permitted, for which agents, under
                which conditions. The spec defines no policy language. No enforcement
                mechanism. No concept of block, warn, or approve. Rules must fire
                before execution — not after.
              </p>
            </div>

            <div className="border-l-4 border-amber-500 pl-5">
              <h3 className="font-bold text-stone-900 mb-1">04 — Isolation</h3>
              <p className="text-sm">
                Prevent lateral movement. An MCP server with network access can make
                outbound requests to internal infrastructure — SSRF is the documented
                attack vector. The spec does not constrain egress. This is a deployment
                and runtime problem that no governance vendor has fully solved.
              </p>
            </div>

            <div className="border-l-4 border-indigo-500 pl-5">
              <h3 className="font-bold text-stone-900 mb-1">05 — Evidence</h3>
              <p className="text-sm">
                Produce audit evidence that survives scrutiny. Not a log file.
                Tamper-evident, cryptographically chained records that a third party
                can verify without access to your infrastructure. Compliance auditors
                do not accept mutable logs.
              </p>
            </div>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-bold text-stone-900 mb-3">An honest scorecard</h2>
          <p>
            Conduct covers Identity, Policy, Evidence, and partial Inventory today —
            shipped in production, not on a roadmap. Isolation at the MCP process level
            is an open gap for us, and for everyone else. We are naming it rather than
            papering over it.
          </p>
          <p className="mt-4">
            Other vendors will ship similar coverage. If they have access to the same
            spec and the same tools, they can build what we built. The differentiated
            layer is narrower: enforcement at the OS hook before any MCP call is issued,
            a hash-chained audit log that does not rely on our infrastructure to verify,
            and a policy engine that fires at three surfaces simultaneously. Those take
            time to build correctly. The protocol compliance parts do not.
          </p>
          <p className="mt-4">
            Most vendors will read the July 28 spec and say they are compliant. Protocol
            compliance is not implementation security. They are not the same thing.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-bold text-stone-900 mb-3">What to do before your next review</h2>
          <ol className="list-decimal pl-5 space-y-3 text-sm">
            <li>
              <strong>Run an MCP inventory.</strong> Know every server your team
              has connected. Most teams cannot answer this in under ten minutes.
              That is the exposure.
            </li>
            <li>
              <strong>Verify tool-call attribution.</strong> For every MCP tool
              call in the last 30 days, can you identify the developer, the agent,
              and the workflow? If not, you have an evidence gap.
            </li>
            <li>
              <strong>Check when policy fires.</strong> Do you have rules that
              fire before tool execution — not after? Post-hoc review is incident
              response. It is not governance.
            </li>
            <li>
              <strong>Audit your egress.</strong> Which MCP servers have outbound
              network access? To what hosts? The 36.7 percent SSRF figure is an
              analysis of production servers, not a hypothetical.
            </li>
          </ol>
        </section>

        <hr className="border-stone-100" />

        <section>
          <p className="text-sm text-stone-500">
            Conduct is runtime AI governance for engineering teams. The hook layer,
            policy engine, and hash-chained audit trail described in this post are
            live in production. If you are running AI agents and want to understand
            your implementation-layer exposure, we can walk through it with you.
          </p>
          <div className="mt-6">
            <CtaLink className="inline-flex rounded-lg bg-stone-900 text-white px-5 py-2.5 text-sm font-semibold hover:bg-stone-700 transition-colors" />
          </div>
        </section>

      </div>
    </article>
  )
}
