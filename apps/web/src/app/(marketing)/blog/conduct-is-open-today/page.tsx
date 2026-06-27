import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Conduct is open today. Here's the honest version. | Conduct",
  description:
    "A launch note from the team behind Conduct. What v1 is, what it isn't, how to onboard in an afternoon, and a standing offer of a free evaluation.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-6">
              <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
                Launch
              </span>
              <span className="text-xs text-stone-400">June 24, 2026</span>
            </div>
            <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
              Conduct is open today. Here&apos;s the honest version.
            </h1>
            <p className="text-lg text-stone-500 leading-relaxed">
              We built Conduct because the problem kept showing up in every
              conversation with engineering leaders, CTOs, CIOs, and CISOs we
              know. It works from day one. This is a launch note: what v1 is,
              what it isn&apos;t, and how to try it without committing to anything.
            </p>
          </div>

          <figure className="mb-10 -mx-2 sm:-mx-6 md:-mx-10">
            <img
              src="/blog/launch-hero.png"
              alt="Conduct Guard dashboard. Overview, Token Abuse Guardrails, By AI tool table with a sample 5-developer team"
              className="w-full rounded-2xl border border-stone-200 shadow-sm"
            />
            <figcaption className="text-xs text-stone-400 text-center mt-3">
              Day one in Conduct. Top: Overview. Middle: Token Abuse Guardrails. Bottom: spend and decisions for the team.
            </figcaption>
          </figure>

          <hr className="border-stone-100 mb-10" />

          <div className="prose prose-stone prose-sm max-w-none space-y-8 text-stone-700 leading-relaxed">

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">The problem we kept hearing</h2>
              <p>
                Every engineering leader, CTO, CIO, and CISO we&apos;ve spoken to over the last year has
                said some version of the same thing. AI is already inside their
                team. Copilot, Cursor, Claude Code, Codex, a dozen MCP servers.
                and nobody can answer simple questions about it.
              </p>
              <p className="mt-4">
                Which models are people using? What did the agent change last
                Tuesday? Did anyone paste a secret into a prompt? Is the SOC 2
                control we wrote down actually being enforced, or is it a PDF
                in a shared drive?
              </p>
              <p className="mt-4">
                None of this is hypothetical. CISOs are being asked these
                questions by their boards. Heads of engineering are being asked
                by their CISOs. The tools that introduced AI into the workflow
                weren&apos;t built to answer them.
              </p>
              <p className="mt-4">
                That&apos;s the gap. Conduct is our attempt to fill it.
              </p>
            </section>

            <section>
              <blockquote className="border-l-4 border-indigo-500 pl-5 py-1 my-2">
                <p className="text-base text-stone-700 leading-relaxed italic mb-3">
                  &ldquo;What impressed me most about Conduct AI is that it approaches AI
                  governance as a business capability, not just a technical feature. By
                  bringing together cost management, security controls, and compliance
                  oversight in a scalable architecture, it addresses a need that many
                  enterprises are actively trying to solve.&rdquo;
                </p>
                <footer className="text-sm text-stone-500">
                  <span className="font-semibold text-stone-700">Ram Prasad</span>
                  {" · "}
                  CEO, Delence
                </footer>
              </blockquote>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">What Conduct is (and isn&apos;t)</h2>
              <p>
                Conduct is an operating layer that sits alongside the AI tools
                your team already uses. It does three things:
              </p>
              <ul className="mt-4 space-y-2 text-sm">
                <li className="flex gap-3">
                  <span className="font-mono text-stone-400 shrink-0 w-16">Govern</span>
                  <span>Policies that travel with your team into Cursor, Claude Code, Copilot. Enforced at the hook level, not after the fact.</span>
                </li>
                <li className="flex gap-3">
                  <span className="font-mono text-stone-400 shrink-0 w-16">Secure</span>
                  <span>Secret scanning, prompt-injection checks, audit-grade activity feed. The evidence trail compliance teams have been improvising.</span>
                </li>
                <li className="flex gap-3">
                  <span className="font-mono text-stone-400 shrink-0 w-16">Automate</span>
                  <span>YAML playbooks for the work that&apos;s already repeated by hand: PR triage, incident response, CI/CD recovery, security review.</span>
                </li>
              </ul>
              <p className="mt-5">
                What it isn&apos;t: a chat product, an IDE replacement, or a new
                model. It&apos;s the layer underneath the things you already pay for,
                making them visible and accountable.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">What&apos;s in v1</h2>
              <p>
                We&apos;ve been deliberate about what shipped today versus what we
                kept on the shelf. v1 is the smallest thing we&apos;d be willing to
                run our own work on.
              </p>
              <div className="mt-5 rounded-xl border border-stone-200 overflow-hidden text-sm">
                <table className="w-full">
                  <thead>
                    <tr className="bg-stone-50 border-b border-stone-200">
                      <th className="text-left px-4 py-3 font-semibold text-stone-600">In v1</th>
                      <th className="text-left px-4 py-3 font-semibold text-stone-600">Not yet</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-100">
                    <tr>
                      <td className="px-4 py-3 text-stone-600">ConductGuard: policy + activity feed</td>
                      <td className="px-4 py-3 text-stone-500">SSO beyond Clerk</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-stone-600">30+ starter playbooks (GitHub, Slack, CI/CD, incident)</td>
                      <td className="px-4 py-3 text-stone-500">On-prem / air-gapped install</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-stone-600">Hook-level telemetry from Claude Code, Cursor, Codex, JetBrains AI Assistant</td>
                      <td className="px-4 py-3 text-stone-500">Self-serve MCP server registry</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-stone-600">Agent Booster + RTK for cost &amp; context efficiency</td>
                      <td className="px-4 py-3 text-stone-500">Custom compliance pack authoring UI</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-stone-600">SOC 2, HIPAA, OWASP starter packs</td>
                      <td className="px-4 py-3 text-stone-500">Multi-region deployment</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p className="mt-5">
                Everything in the right column has a date or a design behind it.
                Nothing on this page is a roadmap promise we don&apos;t intend to keep.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">How to onboard</h2>
              <p>
                We tried to make the first session take an afternoon, not a
                quarter. The shape of it:
              </p>
              <ol className="mt-4 space-y-3 text-sm list-decimal pl-5">
                <li>
                  <strong className="text-stone-900">Sign in.</strong> Email or
                  Google through Clerk. A workspace is created for you.
                </li>
                <li>
                  <strong className="text-stone-900">Connect one tool.</strong>{" "}
                  Claude Code or Cursor is enough. The hook installer is a single
                  command; it takes about a minute.
                </li>
                <li>
                  <strong className="text-stone-900">Pick a compliance pack
                  or a playbook.</strong> SOC 2 if you&apos;re in audit mode, the
                  PR-triage playbook if you want a quick visible win.
                </li>
                <li>
                  <strong className="text-stone-900">Run something real.</strong>{" "}
                  Watch it in the activity feed. Adjust the policy. Re-run.
                </li>
              </ol>
              <p className="mt-4">
                That&apos;s the loop. If you don&apos;t see value by the end of the
                afternoon, we&apos;d rather know than have you wait three weeks to
                find out.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">Free evaluation, flexible partnerships</h2>
              <p>
                We know what it&apos;s like to be on the other side of a vendor pitch
                in the middle of a quarter. So:
              </p>
              <ul className="mt-4 space-y-2 text-sm">
                <li className="flex gap-3">
                  <span className="text-stone-400 shrink-0">·</span>
                  <span><strong className="text-stone-900">60-day free evaluation</strong> for any team with more than a handful of engineers. No credit card, no procurement gauntlet.</span>
                </li>
                <li className="flex gap-3">
                  <span className="text-stone-400 shrink-0">·</span>
                  <span><strong className="text-stone-900">Design-partner slots</strong> for teams that want a say in the next two quarters of roadmap. Reduced pricing in exchange for honest feedback.</span>
                </li>
                <li className="flex gap-3">
                  <span className="text-stone-400 shrink-0">·</span>
                  <span><strong className="text-stone-900">Open-source contributors</strong> get a workspace free, indefinitely. If you maintain something we depend on, you shouldn&apos;t be paying us.</span>
                </li>
                <li className="flex gap-3">
                  <span className="text-stone-400 shrink-0">·</span>
                  <span><strong className="text-stone-900">If pricing is the blocker, write to us.</strong> We&apos;ve done unusual deals for teams whose problem we cared about.</span>
                </li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">Give it a chance?</h2>
              <p>
                We&apos;re aware there&apos;s no shortage of new entrants in this space, and
                we&apos;re not going to claim Conduct is the only answer. What we will
                say is: the problem is real, the people asking us about it are
                serious, and we&apos;ve built something we&apos;d be willing to put under
                our own production work.
              </p>
              <p className="mt-4">
                If any of this resembles a problem you have, we&apos;d like to hear
                from you. An afternoon is a small thing to risk against the chance
                of getting some of those board-level questions answered.
              </p>
              <p className="mt-4 text-stone-500">
                The Conduct team.
              </p>
            </section>

          </div>

          <hr className="border-stone-100 mt-12 mb-8" />
          <div className="flex items-center justify-between text-sm">
            <a href="/blog" className="text-stone-400 hover:text-stone-700 transition-colors">← All posts</a>
            <CtaLink className="inline-flex items-center gap-2 rounded-lg bg-stone-900 text-white px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors">
              Start the afternoon →
            </CtaLink>
          </div>
    </article>
  )
}

