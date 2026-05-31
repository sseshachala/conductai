"use client"

export default function BlogPost() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <BlogNav />
      <main className="flex-1">
        <article className="max-w-2xl mx-auto px-6 py-16">
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-6">
              <span className="text-xs font-semibold text-stone-700 bg-stone-100 border border-stone-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
                RTK
              </span>
              <span className="text-xs text-stone-400">May 31, 2026</span>
            </div>
            <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
              RTK: how we cut 93% of CLI token noise from AI coding sessions.
            </h1>
            <p className="text-lg text-stone-500 leading-relaxed">
              Every time Claude runs a command, the full output lands in the context window.
              A single <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600 text-base">git log</code> can burn 4,000 tokens.
              RTK filters that noise before it ever reaches the model.
            </p>
          </div>

          <hr className="border-stone-100 mb-10" />

          <div className="prose prose-stone prose-sm max-w-none space-y-8 text-stone-700 leading-relaxed">

            <section>
              <p>
                The numbers from our own sessions tell the story. Across 2,221 commands, RTK saved
                <strong> 2.8 million tokens</strong> — a 93.2% reduction. The single biggest win
                was <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600 text-[13px]">rtk read</code>,
                which saved 2.4M tokens across just 42 calls. That&apos;s roughly 57,000 tokens per
                file read, on average, filtered down to what actually matters.
              </p>
              <p className="mt-4">
                This post explains how RTK works and why the savings are so large.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">The problem: tools are chatty</h2>
              <p>
                AI coding tools operate by running shell commands and feeding the output back to the
                model. The model then decides what to do next. This loop is powerful — but the
                raw output of most developer tools is designed for humans, not for language models.
              </p>
              <p className="mt-4">
                Consider what a typical session looks like without filtering:
              </p>

              <div className="mt-4 rounded-xl border border-red-100 bg-red-50 px-5 py-4 text-sm space-y-2">
                <p className="font-semibold text-red-700 text-xs uppercase tracking-widest mb-3">Without RTK — tokens consumed per command</p>
                <div className="flex justify-between text-stone-600"><span><code className="font-mono text-[12px]">git log --oneline -20</code></span><span className="font-mono text-red-600">~800 tokens</span></div>
                <div className="flex justify-between text-stone-600"><span><code className="font-mono text-[12px]">git diff HEAD~1</code></span><span className="font-mono text-red-600">~3,200 tokens</span></div>
                <div className="flex justify-between text-stone-600"><span><code className="font-mono text-[12px]">pnpm install</code></span><span className="font-mono text-red-600">~2,400 tokens</span></div>
                <div className="flex justify-between text-stone-600"><span><code className="font-mono text-[12px]">cat src/app/executor.py</code></span><span className="font-mono text-red-600">~12,000 tokens</span></div>
                <div className="flex justify-between text-stone-600"><span><code className="font-mono text-[12px]">eslint src/</code></span><span className="font-mono text-red-600">~40,000 tokens</span></div>
              </div>

              <p className="mt-5">
                A busy session runs 50–100 commands. Without filtering, that&apos;s millions of
                tokens — most of it noise the model scrolls past anyway.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">What RTK does</h2>
              <p>
                RTK (Rust Token Killer) is a transparent proxy. You prefix any command with{" "}
                <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600 text-[13px]">rtk</code> and
                it intercepts the output, applies a filter matched to that command type, and returns
                only the signal.
              </p>
              <p className="mt-4">
                For commands RTK knows about, it applies a dedicated filter. For commands it doesn&apos;t
                recognise, it passes through unchanged. This means it&apos;s always safe to use — there&apos;s
                no risk of accidentally silencing output RTK doesn&apos;t understand.
              </p>

              <div className="mt-5 rounded-xl border border-stone-200 overflow-hidden text-sm">
                <table className="w-full">
                  <thead>
                    <tr className="bg-stone-50 border-b border-stone-200">
                      <th className="text-left px-4 py-3 font-semibold text-stone-600">Command category</th>
                      <th className="text-left px-4 py-3 font-semibold text-stone-600">Typical savings</th>
                      <th className="text-left px-4 py-3 font-semibold text-stone-600">What gets stripped</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-100">
                    <tr>
                      <td className="px-4 py-3 text-stone-600">Tests (vitest, jest, pytest)</td>
                      <td className="px-4 py-3 font-mono text-emerald-700">90–99%</td>
                      <td className="px-4 py-3 text-stone-500">Passing test names, progress bars, timing</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-stone-600">Build (next, tsc, eslint)</td>
                      <td className="px-4 py-3 font-mono text-emerald-700">70–87%</td>
                      <td className="px-4 py-3 text-stone-500">Route tables, asset sizes, banner ASCII art</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-stone-600">Git (status, log, diff)</td>
                      <td className="px-4 py-3 font-mono text-emerald-700">59–80%</td>
                      <td className="px-4 py-3 text-stone-500">Unchanged files, decorative formatting</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-stone-600">Package managers (pnpm, npm)</td>
                      <td className="px-4 py-3 font-mono text-emerald-700">70–90%</td>
                      <td className="px-4 py-3 text-stone-500">Progress lines, audit noise, dependency tree</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-3 text-stone-600">Infrastructure (docker, kubectl)</td>
                      <td className="px-4 py-3 font-mono text-emerald-700">85%</td>
                      <td className="px-4 py-3 text-stone-500">Container IDs, layer hashes, timestamps</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">The test filter: why 99% is achievable</h2>
              <p>
                The highest savings come from test runners. A typical vitest run for a large project
                might print 800 passing test names, 40 lines of timing breakdown, a progress bar,
                and finally — buried at the bottom — one failing test.
              </p>
              <p className="mt-4">
                The model needs exactly one thing: what failed and why. RTK&apos;s test filter keeps
                only failure blocks and the summary line. Everything else is discarded. That&apos;s
                where the 99.5% figure comes from — not compression, but surgical removal of
                content that carries zero information for the task.
              </p>

              <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-xl bg-red-50 border border-red-100 px-4 py-4">
                  <p className="font-semibold text-red-700 text-xs uppercase tracking-widest mb-3">Raw vitest output</p>
                  <div className="font-mono text-xs text-stone-500 space-y-0.5">
                    <p>✓ auth.test.ts (42 tests)</p>
                    <p>✓ user.test.ts (18 tests)</p>
                    <p>✓ api.test.ts (31 tests)</p>
                    <p className="text-stone-300">... 790 more passing lines</p>
                    <p className="text-red-500 mt-2">✕ executor.test.ts</p>
                    <p className="text-red-400">  AssertionError: expected…</p>
                    <p className="text-stone-400 mt-2">Duration: 14.2s</p>
                  </div>
                </div>
                <div className="rounded-xl bg-emerald-50 border border-emerald-100 px-4 py-4">
                  <p className="font-semibold text-emerald-700 text-xs uppercase tracking-widest mb-3">RTK output</p>
                  <div className="font-mono text-xs text-stone-500 space-y-0.5">
                    <p className="text-red-500">✕ executor.test.ts</p>
                    <p className="text-red-400">  AssertionError: expected…</p>
                    <p className="mt-2 text-stone-400">1 failed, 881 passed</p>
                  </div>
                </div>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">The CLAUDE.md hook</h2>
              <p>
                RTK integrates via a hook in <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600 text-[13px]">CLAUDE.md</code>.
                Once configured, Claude Code automatically prefixes commands with{" "}
                <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600 text-[13px]">rtk</code> — you don&apos;t have to remember to do it manually.
                The savings accumulate silently across every session.
              </p>
              <p className="mt-4">
                Track them any time:
              </p>
              <div className="mt-3 rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm space-y-1">
                <p className="text-emerald-400">rtk gain</p>
                <p className="text-stone-400 mt-2">Total commands:    2221</p>
                <p className="text-stone-400">Tokens saved:      2.8M (93.2%)</p>
                <p className="text-stone-400">Efficiency:        ████████████████████░░ 93.2%</p>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">RTK as Layer 2</h2>
              <p>
                RTK sits at Layer 2 of the Agent Booster stack — between prompt caching (Layer 1)
                and AST-level symbol routing (Layer 3). The three layers compound:
              </p>
              <ul className="mt-4 space-y-2 text-sm">
                <li className="flex gap-3">
                  <span className="font-mono text-stone-400 shrink-0">L1</span>
                  <span>Prompt caching cuts cost on stable context that&apos;s already been sent.</span>
                </li>
                <li className="flex gap-3">
                  <span className="font-mono text-stone-400 shrink-0">L2</span>
                  <span>RTK cuts the volume of tool output before it enters the context window.</span>
                </li>
                <li className="flex gap-3">
                  <span className="font-mono text-stone-400 shrink-0">L3</span>
                  <span>Agent Booster cuts what code the model reads — AST routing, smart_read, route_model.</span>
                </li>
              </ul>
              <p className="mt-5">
                Together they&apos;re responsible for the bulk of the 3–15x cost reduction we see
                in production sessions. RTK alone accounts for the 93% CLI noise reduction
                shown above.
              </p>
            </section>

          </div>

          <hr className="border-stone-100 mt-12 mb-8" />
          <div className="flex items-center justify-between text-sm">
            <a href="/blog" className="text-stone-400 hover:text-stone-700 transition-colors">← All posts</a>
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
      <a href="/"><img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" /></a>
      <div className="flex items-center gap-4">
        <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
        <a href="/products/agent-booster" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Agent Booster</a>
        <a href="/marketplace" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Playbooks</a>
        <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
      </div>
    </header>
  )
}
