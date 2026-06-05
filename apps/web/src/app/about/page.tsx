export default function AboutPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <header className="px-6 py-5 flex items-center justify-between max-w-6xl mx-auto w-full">
        <a href="/">
          <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
        </a>
        <div className="flex items-center gap-4">
          <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
          <a href="/tools" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Tools</a>
          <a href="/marketplace" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Agent Templates</a>
          <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">GitHub</a>
        </div>
      </header>

      <main className="flex-1 max-w-2xl mx-auto px-6 py-16 w-full">

        {/* Name + intro */}
        <div className="mb-12">
          <div className="w-16 h-16 rounded-full bg-stone-900 flex items-center justify-center text-white text-xl font-bold mb-6">
            S
          </div>
          <h1 className="text-4xl font-bold text-stone-900 mb-4 leading-tight">
            Sudhi Seshachala
          </h1>
          <p className="text-lg text-stone-500 leading-relaxed">
            AI enthusiast. Failed founder. Open-source builder.
            Houston, TX.
          </p>
        </div>

        <hr className="border-stone-100 mb-12" />

        <div className="space-y-10 text-stone-700 leading-relaxed">

          {/* The failure */}
          <section>
            <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">The backstory</h2>
            <p>
              I built <strong>Xervmon</strong> — a cloud management and monitoring platform — and spent years
              trying to turn it into a business. It didn&apos;t work. Not for lack of effort or conviction,
              but because the timing was off, the market moved differently than I expected, and building
              a company is genuinely hard in ways that aren&apos;t obvious from the outside.
            </p>
            <p className="mt-4">
              I learned more from that failure than from anything else I&apos;ve done. About what engineers
              actually need. About where tools break down at scale. About the gap between what sounds
              good in a pitch and what actually gets used at 2am when something is on fire.
            </p>
          </section>

          {/* The return */}
          <section>
            <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">The return</h2>
            <p>
              AI changed everything — not as a buzzword, but as a genuine shift in what a single
              developer can build and ship. I got obsessed. I started using Claude Code, building
              agentic workflows, wiring up MCP servers, and watching my token bills climb.
            </p>
            <p className="mt-4">
              And I noticed the same pattern that killed Xervmon: powerful tools with rough edges.
              Context replay burning thousands of dollars a day. Models routing to Opus when Haiku
              would do. Files read in full when three functions would suffice.
            </p>
            <p className="mt-4">
              This time I&apos;m not building a business around the fix. <strong>I&apos;m just shipping it.</strong>
            </p>
          </section>

          {/* The philosophy */}
          <section>
            <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">The philosophy</h2>
            <p>
              Every idea I have, every tool I build, every pattern I discover — it goes on GitHub.
              MIT licensed. No freemium gates. No &ldquo;contact us for enterprise pricing.&rdquo;
            </p>
            <p className="mt-4">
              If it&apos;s useful, fork it. Improve it. Use it at 2am when something is on fire.
              That&apos;s what I wanted from Xervmon. That&apos;s what I&apos;m building now.
            </p>
            <p className="mt-4">
              The tools I&apos;m shipping — Agent Booster, RTK, Conduct — are the infrastructure
              I wish had existed when I was running Xervmon. Context efficiency, smart model routing,
              governed agent workflows that a team can actually own and modify as YAML. Small, composable,
              open.
            </p>
          </section>

          {/* What I'm building */}
          <section>
            <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">What I&apos;m building</h2>

            <div className="space-y-4">
              <div className="rounded-xl border border-stone-200 px-5 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-semibold text-stone-900">Agent Booster</p>
                    <p className="text-sm text-stone-500 mt-1">
                      AST-level context routing for AI coding tools. smart_read, semantic search,
                      smart model routing. Cut Claude Code costs 3–15x.
                    </p>
                  </div>
                  <a href="/tools/agent-booster" className="shrink-0 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors mt-0.5">
                    Learn more →
                  </a>
                </div>
              </div>

              <div className="rounded-xl border border-stone-200 px-5 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-semibold text-stone-900">RTK — Rust Token Killer</p>
                    <p className="text-sm text-stone-500 mt-1">
                      A transparent CLI proxy that strips token noise from git, build, test, and
                      package manager output before it reaches the model. 93% savings in production.
                    </p>
                  </div>
                  <a href="/blog/rtk-how-we-cut-93-percent-of-cli-tokens" className="shrink-0 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors mt-0.5">
                    Read post →
                  </a>
                </div>
              </div>

              <div className="rounded-xl border border-stone-200 px-5 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-semibold text-stone-900">Conduct</p>
                    <p className="text-sm text-stone-500 mt-1">
                      Governed AI automations for tickets, PRs, alerts, and incidents. Install a
                      playbook, connect an environment, and run.
                    </p>
                  </div>
                  <a href="/marketplace" className="shrink-0 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors mt-0.5">
                    Browse →
                  </a>
                </div>
              </div>
            </div>
          </section>

          {/* Find me */}
          <section>
            <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">Find me</h2>
            <div className="flex flex-wrap gap-4">
              <a
                href="https://github.com/sseshachala/conductai"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-lg border border-stone-200 px-4 py-2.5 text-sm font-medium text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
              >
                <GitHubIcon />
                GitHub
              </a>
              <a
                href="mailto:sudhi@b2bsphere.com"
                className="inline-flex items-center gap-2 rounded-lg border border-stone-200 px-4 py-2.5 text-sm font-medium text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
              >
                <MailIcon />
                sudhi@b2bsphere.com
              </a>
            </div>
            <p className="mt-5 text-sm text-stone-400">
              If you&apos;re building with AI agents and want to compare notes, I&apos;m always up for it.
            </p>
          </section>

        </div>
      </main>

      <footer className="border-t border-stone-100 py-8 text-center text-xs text-stone-400">
        <p>Built with love from Houston · <a href="/" className="hover:text-stone-600 transition-colors">Conduct AI</a></p>
      </footer>
    </div>
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
