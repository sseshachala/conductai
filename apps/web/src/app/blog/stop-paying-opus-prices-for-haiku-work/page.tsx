"use client"

export default function BlogPost() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <BlogNav />
      <main className="flex-1">
        <article className="max-w-2xl mx-auto px-6 py-16">
          {/* Meta */}
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-6">
              <span className="text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
                Agent Booster
              </span>
              <span className="text-xs text-stone-400">May 31, 2026</span>
            </div>
            <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
              Stop paying Opus prices for Haiku work.
            </h1>
            <p className="text-lg text-stone-500 leading-relaxed">
              Most AI coding setups default to the most capable model for every task — including fixing a typo.
              That&apos;s a 4x cost penalty on work a cheaper model handles just as well.
            </p>
          </div>

          <hr className="border-stone-100 mb-10" />

          {/* Body */}
          <div className="prose prose-stone prose-sm max-w-none space-y-8 text-stone-700 leading-relaxed">

            <section>
              <p>
                Reuven Cohen put it plainly: the going rate for a single developer running Claude Code in
                swarm mode is <strong>~$2,500/day</strong>. Not because the models are expensive — because
                the same context keeps getting resent, and because every task, regardless of complexity,
                gets routed to the heaviest model available.
              </p>
              <p className="mt-4">
                Fixing a typo in an error message does not require Opus. Renaming a variable does not
                require Opus. Adding a log line does not require Opus. But if your tooling doesn&apos;t
                know that, it will happily bill you as if it does.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">The routing table</h2>
              <p>
                Agent Booster&apos;s new <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-amber-700 text-[13px]">route_model</code> tool
                applies three signals to decide which model tier to recommend:
              </p>

              <div className="mt-5 rounded-xl border border-stone-200 overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-stone-50 border-b border-stone-200">
                      <th className="text-left px-4 py-3 font-semibold text-stone-600">Signal</th>
                      <th className="text-left px-4 py-3 font-semibold text-stone-600">Model</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-100">
                    <tr>
                      <td className="px-4 py-3 text-stone-600">Complexity keyword: <em>refactor, architect, design, migrate, security…</em></td>
                      <td className="px-4 py-3 font-semibold text-violet-700">Opus</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-stone-600">Task touches 5+ distinct files</td>
                      <td className="px-4 py-3 font-semibold text-violet-700">Opus</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-stone-600">Task touches 2–4 files</td>
                      <td className="px-4 py-3 font-semibold text-blue-700">Sonnet</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-stone-600">1 file, fewer than 3 matching symbols</td>
                      <td className="px-4 py-3 font-semibold text-emerald-700">Haiku</td>
                    </tr>
                    <tr className="bg-stone-50">
                      <td className="px-4 py-3 text-stone-500">Everything else</td>
                      <td className="px-4 py-3 font-semibold text-blue-700">Sonnet (default)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">How it works</h2>
              <p>
                When you call <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-amber-700 text-[13px]">route_model(task)</code>,
                Booster first checks the task description for complexity keywords.
                If none match, it runs a vector search across your indexed codebase to count how many distinct
                files are semantically relevant. Narrow task, few files, few symbols → Haiku.
                Broad cross-cutting task → Opus.
              </p>
              <p className="mt-4">
                The result is a JSON object the calling agent can act on immediately:
              </p>

              <div className="mt-4 rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm space-y-1">
                <p className="text-stone-500"># narrow task</p>
                <p className="text-emerald-400">{"{"} &quot;model&quot;: &quot;haiku&quot;, &quot;reason&quot;: &quot;narrow task — 1 symbol in 1 file&quot; {"}"}</p>
                <p className="mt-3 text-stone-500"># architecture change</p>
                <p className="text-emerald-400">{"{"} &quot;model&quot;: &quot;opus&quot;, &quot;reason&quot;: &quot;complexity keyword: refactor&quot; {"}"}</p>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">Using it from the CLI</h2>
              <p>
                You don&apos;t need to be inside an MCP session to use it. The CLI command works anywhere in your project:
              </p>

              <div className="mt-4 space-y-3">
                <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm">
                  <p className="text-stone-500 text-xs mb-2"># returns the recommended tier before you start</p>
                  <p className="text-emerald-400">booster route &quot;fix typo in error message&quot;</p>
                  <p className="text-stone-400 mt-1">haiku  (narrow task — 1 symbol in 1 file)</p>
                </div>
                <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm">
                  <p className="text-emerald-400">booster route &quot;refactor auth middleware to support OAuth2&quot;</p>
                  <p className="text-stone-400 mt-1">opus  (complexity keyword: refactor)</p>
                </div>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">Where this fits in the stack</h2>
              <p>
                Agent Booster operates at three compounding layers:
              </p>
              <ul className="mt-4 space-y-2 list-none pl-0">
                <li className="flex gap-3 items-start">
                  <span className="mt-0.5 w-5 h-5 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center shrink-0 text-xs font-bold">3</span>
                  <span><strong>AST + semantic routing</strong> — smart_read, search_context, get_symbols, route_model. Reduces what the model sees per call.</span>
                </li>
                <li className="flex gap-3 items-start">
                  <span className="mt-0.5 w-5 h-5 rounded-full bg-stone-100 border border-stone-200 text-stone-500 flex items-center justify-center shrink-0 text-xs font-bold">2</span>
                  <span><strong>RTK</strong> — strips noise from CLI, git, build, and test output before it enters the context window.</span>
                </li>
                <li className="flex gap-3 items-start">
                  <span className="mt-0.5 w-5 h-5 rounded-full bg-stone-100 border border-stone-200 text-stone-500 flex items-center justify-center shrink-0 text-xs font-bold">1</span>
                  <span><strong>Prompt caching</strong> — stable prefixes cached at 90% discount. Native to Claude Code and the Anthropic API.</span>
                </li>
              </ul>
              <p className="mt-4">
                <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-amber-700 text-[13px]">route_model</code> is the newest addition to Layer 3.
                It doesn&apos;t change what context is sent — it changes which model receives it.
                Combined with smart_read already cutting token volume 3–15x, routing to Haiku on narrow tasks
                compounds the savings further.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">Get it</h2>
              <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm space-y-1">
                <p className="text-stone-500 text-xs mb-2"># install</p>
                <p className="text-emerald-400">pip install agent-booster</p>
                <p className="mt-3 text-stone-500 text-xs mb-2"># index your codebase</p>
                <p className="text-emerald-400">booster index</p>
                <p className="mt-3 text-stone-500 text-xs mb-2"># route a task</p>
                <p className="text-emerald-400">booster route &quot;your task here&quot;</p>
              </div>
              <p className="mt-5 text-sm text-stone-500">
                The MCP tool is available automatically once you run{" "}
                <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600 text-[13px]">booster init claude</code>.
                No config changes needed — it shows up alongside get_symbols, search_context, and smart_read.
              </p>
            </section>

          </div>

          {/* Footer */}
          <hr className="border-stone-100 mt-12 mb-8" />
          <div className="flex items-center justify-between text-sm">
            <a href="/blog" className="text-stone-400 hover:text-stone-700 transition-colors">
              ← All posts
            </a>
            <a
              href="/products/agent-booster"
              className="inline-flex items-center gap-2 rounded-lg bg-stone-900 text-white px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors"
            >
              Agent Booster →
            </a>
          </div>
        </article>
      </main>
    </div>
  )
}

function BlogNav() {
  return (
    <header className="px-6 py-5 flex items-center justify-between max-w-6xl mx-auto w-full">
      <a href="/">
        <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
      </a>
      <div className="flex items-center gap-4">
        <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
        <a href="/products/agent-booster" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Agent Booster</a>
        <a href="/marketplace" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Playbooks</a>
        <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
      </div>
    </header>
  )
}
