export default function AboutPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">

      <header className="px-6 py-4 flex items-center justify-between max-w-6xl mx-auto w-full sticky top-0 bg-white/95 backdrop-blur-sm z-50 border-b border-stone-100">
        <a href="/"><img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" /></a>
        <nav className="hidden md:flex items-center gap-6">
          <SolutionsDropdown />
          <ToolsDropdown />
          <a href="/marketplace" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Marketplace</a>
          <a href="/partners" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Partners</a>
          <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
          <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
        </nav>
        <div className="flex items-center gap-3">
          <a href="mailto:hello@conductai.ai" className="text-sm font-medium text-stone-600 hover:text-stone-900 transition-colors hidden sm:block">Talk to Us</a>
          <a href="/sign-up" className="rounded-lg bg-stone-900 text-white px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors">Start Free</a>
        </div>
      </header>

      <main className="flex-1 max-w-xl mx-auto px-6 py-20 w-full">

        <div className="mb-16">
          <div className="w-14 h-14 rounded-full bg-stone-900 flex items-center justify-center text-white text-lg font-bold mb-8">C</div>
          <h1 className="text-4xl font-black text-stone-900 tracking-tight leading-tight mb-3">
            A team of builders.
          </h1>
          <p className="text-stone-400 text-sm">Houston, TX &nbsp;·&nbsp; One of us founded Xervmon &nbsp;·&nbsp; All of us have been burned by the gap we&apos;re closing</p>
        </div>

        <div className="space-y-10 text-stone-700 leading-[1.9] text-[1.0625rem]">

          <p>
            I gave the best years of my career to a company called <strong className="text-stone-900 font-semibold">Xervmon</strong>.
            Cloud management. Monitoring. Infrastructure visibility.
            I believed in it the way you only believe in something
            you&apos;ve poured yourself into completely — nights, weekends, savings, relationships.
            All of it.
          </p>

          <p className="text-stone-500 italic border-l-2 border-stone-200 pl-5">
            It didn&apos;t make it.
          </p>

          <p>
            Not because the technology was wrong. Not because the team didn&apos;t work hard.
            The market moved. The timing was off. The gap between what we built and what
            customers were willing to pay for turned out to be wider than any amount of
            conviction could bridge.
          </p>

          <p>
            I remember the exact moment I knew. Sitting in a conference room, looking at
            a spreadsheet that told a story I had been refusing to read for months.
            The numbers didn&apos;t argue. They just sat there.
          </p>

          <p>
            Shutting it down quietly is the loneliest thing I&apos;ve ever done.
            There&apos;s no public announcement. No closure. You just stop.
            And then you figure out who you are when the thing you were
            is gone.
          </p>

          <p>
            It took me ten years to recover. Not ten months. Ten years.
          </p>

          <p>
            My family held me together during that time in ways I am still
            finding words for. Friends who didn&apos;t ask when I was going
            to figure it out. Who just stayed. I don&apos;t think I understood
            what that cost them until much later.
          </p>

          <p className="text-stone-500 italic border-l-2 border-stone-200 pl-5">
            Recently, I reached out to our seed investor to apologize.
            It had taken me years to find the courage to even send the message.
            I didn&apos;t have a face to show them for a long time.
            They were gracious. That generosity still humbles me.
          </p>

          <p>
            Even today — with Conduct growing, with new customers, with a product
            I believe in — my primary obligation is to them. To our seed investor.
            To the handful of others who stood with us like a rock when there was
            no rational reason to. Partners who didn&apos;t just write a check
            but showed up, stayed in, and never made me feel small for failing.
          </p>

          <p>
            I don&apos;t think of Conduct as a second chance.
            I think of it as a debt I intend to repay — not just in money,
            but in something built that lasts. Something that justifies the
            trust that was placed in me when I hadn&apos;t yet earned it.
          </p>

          <hr className="border-stone-100" />

          <p>
            What I took from Xervmon wasn&apos;t bitterness. It was clarity.
            I understood, finally and specifically, where tools break under pressure.
            Where governance becomes a document nobody reads. Where visibility
            disappears exactly when you need it most. Where engineering teams
            make decisions at 2am with no safety net and no record of what happened.
          </p>

          <p>
            That knowledge sat in me for a long time.
          </p>

          <p>
            Then AI arrived — not as a trend, but as a genuine rupture in what one person
            could build and ship. I started building with it. Claude Code, agentic workflows,
            MCP servers. The token bills climbed. The context costs were brutal.
            And I noticed the familiar pattern: powerful tools, invisible risks, and
            nobody owning the layer underneath.
          </p>

          <p>
            Engineering teams adopting AI with no controls. No audit trail.
            No visibility into what their AI tools were actually doing.
            Credentials leaking into prompts. Security policies that existed on paper
            and nowhere else. Compliance teams asking questions that nobody could answer.
          </p>

          <p>
            I had watched this exact failure mode destroy something I built.
            I wasn&apos;t going to watch it happen to other people&apos;s teams.
          </p>

          <p className="text-stone-900 font-semibold">
            So I built Conduct AI.
          </p>

          <p>
            Not as a pivot. Not as a market opportunity I spotted on a slide deck.
            As the thing I needed to exist. The governance layer that runs at the same
            layer as the tools — not above them in a policy document, not below them
            in infrastructure nobody configures. Right there, between the developer
            and the AI, enforcing the rules in real time.
          </p>

          <p>
            Guard for every AI session. Security enforcement in every PR.
            Workflows that inherit your policies instead of running around them.
            An audit trail that can actually answer the compliance question —
            not in theory, but in one click.
          </p>

          <hr className="border-stone-100" />

          <p className="text-stone-500">
            Along the way, I built tools to make AI work better at the engineering
            layer. Because the infrastructure underneath the governance matters too.
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
                name: "RTK — Rust Token Killer",
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
            Everything goes on GitHub. MIT licensed. No gates. No &ldquo;contact sales&rdquo;
            before you can see what you&apos;re buying. The Xervmon years taught me
            that the people who actually need a tool find out too late when it&apos;s
            hidden behind a demo request form.
          </p>

          <p className="text-stone-500">
            If you&apos;re building in this space and want to compare notes —
            or if you just want to talk to someone who has failed loudly enough
            to know what actually matters — I&apos;m here.
          </p>

          <div className="flex flex-wrap gap-3 pt-2 pb-4">
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
              href="mailto:hello@conductai.ai"
              className="inline-flex items-center gap-2 rounded-lg border border-stone-200 px-4 py-2.5 text-sm font-medium text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
            >
              <MailIcon />
              hello@conductai.ai
            </a>
          </div>

        </div>
      </main>

      <footer className="border-t border-stone-100 py-8 px-6 bg-white">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row justify-between items-center gap-4 text-xs text-stone-400">
          <div className="flex items-center gap-4 flex-wrap justify-center">
            <span>© {new Date().getFullYear()} Conduct AI</span>
            <a href="/" className="hover:text-stone-600 transition-colors">Home</a>
            <a href="/solutions" className="hover:text-stone-600 transition-colors">Solutions</a>
            <a href="/partners" className="hover:text-stone-600 transition-colors">Partners</a>
            <a href="/docs" className="hover:text-stone-600 transition-colors">Docs</a>
            <a href="/privacy" className="hover:text-stone-600 transition-colors">Privacy</a>
            <a href="/terms" className="hover:text-stone-600 transition-colors">Terms</a>
          </div>
          <span className="text-stone-300">Envisioned, designed and developed with love from Houston</span>
        </div>
      </footer>

    </div>
  )
}

function SolutionsDropdown() {
  return (
    <div className="relative group">
      <a href="/solutions" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Solutions
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[220px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/solutions#guard" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🛡️</span><div><p className="font-semibold">Conduct Guard</p><p className="text-xs text-stone-400">AI session governance</p></div>
          </a>
          <a href="/solutions#secure" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🔒</span><div><p className="font-semibold">Secure</p><p className="text-xs text-stone-400">Automated security enforcement</p></div>
          </a>
          <a href="/solutions#workflows" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>⚡</span><div><p className="font-semibold">Agentic Workflows</p><p className="text-xs text-stone-400">Governed AI automations</p></div>
          </a>
          <a href="/solutions#sdd" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>📐</span><div><p className="font-semibold">Spec-Driven Dev</p><p className="text-xs text-stone-400">Intent-first AI coding</p></div>
          </a>
          <a href="/marketplace" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>📦</span><div><p className="font-semibold">Playbooks</p><p className="text-xs text-stone-400">Pre-built AI automations</p></div>
          </a>
          <div className="border-t border-stone-100 mt-1 pt-1">
            <a href="/solutions" className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors">View all solutions →</a>
          </div>
        </div>
      </div>
    </div>
  )
}

function ToolsDropdown() {
  return (
    <div className="relative group">
      <a href="/tools" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Tools
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[200px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/tools/agent-booster" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-indigo-600 font-bold text-base">◈</span><div><p className="font-semibold">Agent Booster</p><p className="text-xs text-stone-400">Cut AI costs 3–15×</p></div>
          </a>
          <a href="/tools/conduct-cli" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-violet-600 font-bold text-base">⬡</span><div><p className="font-semibold">Conduct CLI</p><p className="text-xs text-stone-400">Govern from the terminal</p></div>
          </a>
          <a href="/tools/security-loop" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-rose-600 font-bold text-base">🔐</span><div><p className="font-semibold">Security Loop</p><p className="text-xs text-stone-400">Automated PR scanning</p></div>
          </a>
        </div>
      </div>
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
