export default function AboutPage() {
  return (
    <main className="flex-1 max-w-xl mx-auto px-6 py-20 w-full">

      <div className="mb-16">
        <div className="w-14 h-14 rounded-full bg-stone-900 flex items-center justify-center text-white text-lg font-bold mb-8">C</div>
        <h1 className="text-4xl font-black text-stone-900 tracking-tight leading-tight mb-3">
          A team of builders.
        </h1>
        <p className="text-stone-400 text-sm">Houston, TX &nbsp;·&nbsp; Building governance for AI-assisted engineering teams</p>
      </div>

      <div className="space-y-8 text-stone-700 leading-[1.8] text-[1.0625rem]">

        <p>
          Conduct AI is built by engineers who ran cloud infrastructure
          and observability teams for the better part of a decade. Before
          this we built and ran <strong className="text-stone-900 font-semibold">Xervmon</strong>,
          a cloud management platform, the kind of product that taught us
          exactly where governance tools break under pressure, where audit
          trails go quiet at the moment they&apos;re needed, and where the
          gap between a written policy and an enforced policy can swallow
          a company whole.
        </p>

        <p>
          Xervmon didn&apos;t survive. The market wasn&apos;t there yet.
          What did survive was a very specific understanding of how
          engineering teams actually make decisions when things break,
          and what kind of safety net is, and isn&apos;t, there when
          they do.
        </p>

        <p>
          When AI arrived as a real shift in what a small team could
          build, we started shipping with it. Claude Code, MCP servers,
          agentic playbooks. The pattern was familiar: powerful tools,
          invisible risks, no clear owner for the layer underneath.
          Credentials drifting into prompts, policies that existed only
          on paper, no answer to the compliance question the auditor
          would ask in six months.
        </p>

        <p className="text-stone-900 font-semibold">
          That&apos;s why Conduct AI exists.
        </p>

        <p>
          We build the governance layer at the same layer as the tools —
          not above them in a policy document, not below them in
          infrastructure no one configures. Guard policies enforced in
          every AI session. Security checks in every PR. Workflows that
          inherit your rules instead of routing around them. An audit
          trail that answers the compliance question in one click,
          not one quarter.
        </p>

        <hr className="border-stone-100" />

        <p className="text-stone-500 text-sm">
          Along the way we built infrastructure to make AI work better
          at the engineering layer. These tools are free and open source —
          they fund and dogfood the platform.
        </p>

        <div className="space-y-4">
          {[
            {
              name: "Agent Booster",
              desc: "AST-level context routing. Reads only what the task needs. Cut Claude Code costs 3–15×.",
              href: "/tools/agent-booster",
              label: "Learn more",
            },
            {
              name: "RTK: Rust Token Killer",
              desc: "Strips noise from git, build, and test output before it reaches the model. 93% savings in production.",
              href: "/blog/rtk-how-we-cut-93-percent-of-cli-tokens",
              label: "Read post",
            },
            {
              name: "Conduct CLI",
              desc: "Run governance from the terminal. Sync Guard policies, trigger workflows, install playbooks.",
              href: "/tools/conduct-cli",
              label: "See the CLI",
            },
          ].map(tool => (
            <div key={tool.name} className="rounded-xl border border-stone-200 px-5 py-4 hover:border-stone-300 transition-colors">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-semibold text-stone-900 mb-1">{tool.name}</p>
                  <p className="text-sm text-stone-500 leading-relaxed">{tool.desc}</p>
                </div>
                <a href={tool.href} className="shrink-0 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors mt-0.5 whitespace-nowrap">
                  {tool.label} →
                </a>
              </div>
            </div>
          ))}
        </div>

        <hr className="border-stone-100" />

        <p>
          Source on GitHub, MIT licensed. No demo gates before you can
          see what you&apos;re buying.
        </p>

        <p className="text-stone-500 text-sm">
          If you&apos;re building in this space and want to compare notes,
          we&apos;re reachable below.
        </p>

        <div className="flex flex-wrap gap-3 pt-2 pb-4">
          <a
            href="https://github.com/sseshachala/conduct-cli"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-stone-200 px-4 py-2.5 text-sm font-medium text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
          >
            <GitHubIcon />
            GitHub
          </a>
          <a
            href="mailto:hello@conductai.ai"
            className="inline-flex items-center gap-2 rounded-lg border border-stone-200 px-4 py-2.5 text-sm font-medium text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
          >
            <MailIcon />
            hello@conductai.ai
          </a>
          <a
            href="https://cal.com/sudhi-seshachala-pks7pd"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-stone-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-stone-700 transition-all"
          >
            Book a Demo
          </a>
        </div>

      </div>
    </main>
  )
}

function GitHubIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

function MailIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="1" y="3" width="14" height="10" rx="1.5" />
      <path d="M1 4.5l7 5 7-5" />
    </svg>
  )
}
