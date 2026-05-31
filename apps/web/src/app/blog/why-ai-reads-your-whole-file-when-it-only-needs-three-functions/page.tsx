"use client"

export default function BlogPost() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <BlogNav />
      <main className="flex-1">
        <article className="max-w-2xl mx-auto px-6 py-16">
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-6">
              <span className="text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
                Agent Booster
              </span>
              <span className="text-xs text-stone-400">May 31, 2026</span>
            </div>
            <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
              Why your AI reads the whole file when it only needs three functions.
            </h1>
            <p className="text-lg text-stone-500 leading-relaxed">
              AI coding tools aren&apos;t lazy — they&apos;re blind. They can&apos;t see inside a file
              without reading it. Agent Booster gives them a map so they don&apos;t have to.
            </p>
          </div>

          <hr className="border-stone-100 mb-10" />

          <div className="prose prose-stone prose-sm max-w-none space-y-8 text-stone-700 leading-relaxed">

            <section>
              <p>
                Imagine asking a colleague to fix a bug in a 2,000-line file. A good engineer
                skims the structure, finds the relevant function, reads it, and fixes it.
                They don&apos;t read all 2,000 lines.
              </p>
              <p className="mt-4">
                An AI coding tool, by default, does read all 2,000 lines. Not because it&apos;s
                inefficient — but because it has no other choice. It can&apos;t see the shape of a
                file without reading it. Every read is a full read.
              </p>
              <p className="mt-4">
                This post explains how Agent Booster solves that — and what an AST actually is,
                in plain terms.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">What is an AST?</h2>
              <p>
                AST stands for Abstract Syntax Tree. It sounds technical. It&apos;s actually a simple idea.
              </p>
              <p className="mt-4">
                When you write code, you&apos;re writing text. But that text has structure —
                functions, classes, arguments, return values. An AST is just a structured
                representation of that text. Instead of treating your file as a long string of
                characters, an AST treats it as a tree of named parts.
              </p>

              <div className="mt-5 rounded-xl border border-stone-200 bg-stone-50 px-6 py-5">
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">A 1,800-line file, two ways</p>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="font-semibold text-stone-700 mb-2">As raw text</p>
                    <p className="text-stone-500 text-xs leading-relaxed">
                      1,800 lines of characters. To find anything, you read from the top. There&apos;s no
                      index. No structure. Just text.
                    </p>
                  </div>
                  <div>
                    <p className="font-semibold text-indigo-700 mb-2">As an AST</p>
                    <p className="text-stone-500 text-xs leading-relaxed">
                      A map: 42 functions, 8 classes. Each with a name, line range, and signature.
                      You jump straight to what you need.
                    </p>
                  </div>
                </div>
              </div>

              <p className="mt-5">
                Agent Booster uses a tool called <strong>tree-sitter</strong> to parse your
                codebase into an AST when you run <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600 text-[13px]">booster index</code>.
                The result is stored in a small local database — a symbol index.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">The symbol index</h2>
              <p>
                After indexing, Booster knows about every function and class in your project:
                its name, which file it lives in, which lines it spans, and its signature
                (the first line — the part that tells you what it accepts and returns).
              </p>
              <p className="mt-4">
                Nothing is sent anywhere. It&apos;s a local SQLite file at{" "}
                <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600 text-[13px]">.booster/symbols.db</code>.
              </p>

              <div className="mt-5 rounded-xl bg-stone-950 px-5 py-4 font-mono text-xs space-y-1 text-stone-400">
                <p className="text-stone-500 mb-2"># what the index knows about a single file</p>
                <p><span className="text-indigo-400">function</span> execute_block       lines 45–89    (block, state, db)</p>
                <p><span className="text-indigo-400">function</span> _write_trace        lines 126–136  (db, run_id, block_id, ...)</p>
                <p><span className="text-indigo-400">function</span> _emit               lines 139–145  (db, run_id, block_id, kind, payload)</p>
                <p><span className="text-indigo-400">function</span> _execute_output     lines 1165–1252 (block, state, credentials, ...)</p>
                <p className="text-stone-600 mt-2">... 38 more symbols in this file</p>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">smart_read: the surgeon</h2>
              <p>
                When Claude needs to read a file, it normally calls a read tool and gets back
                the whole thing. With Agent Booster installed,{" "}
                <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600 text-[13px]">smart_read</code> intercepts
                that call.
              </p>
              <p className="mt-4">
                It takes two inputs: the file path and a description of the task. It looks
                up that file in the symbol index, matches the task description against the symbol
                names, and returns only the source lines for the matching functions — with
                a header showing exactly where they came from.
              </p>

              <div className="mt-5 grid grid-cols-2 gap-3 text-xs">
                <div className="rounded-xl border border-red-100 bg-red-50 px-4 py-4">
                  <p className="font-semibold text-red-700 uppercase tracking-widest text-[10px] mb-3">Without smart_read</p>
                  <p className="text-stone-500 leading-relaxed">
                    Claude reads <code className="font-mono">executor.py</code>.<br />
                    Gets back 1,800 lines.<br />
                    ~14,000 tokens consumed.<br />
                    Finds the 3 functions it needed on lines 126–145.
                  </p>
                </div>
                <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-4">
                  <p className="font-semibold text-indigo-700 uppercase tracking-widest text-[10px] mb-3">With smart_read</p>
                  <p className="text-stone-500 leading-relaxed">
                    Claude calls smart_read with task &ldquo;write trace row&rdquo;.<br />
                    Gets back 22 lines.<br />
                    ~170 tokens consumed.<br />
                    Same result. 98% fewer tokens.
                  </p>
                </div>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">Semantic search: finding the right file first</h2>
              <p>
                Sometimes you don&apos;t know which file to read. You just know what you&apos;re trying to do.
              </p>
              <p className="mt-4">
                <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600 text-[13px]">search_context</code> handles this.
                It takes your task description and searches the symbol index by meaning — not just
                keyword matching. It uses a small local embedding model to understand that
                &ldquo;handle Slack notification failure&rdquo; and &ldquo;post_message error handling&rdquo; are related,
                even if they share no words.
              </p>
              <p className="mt-4">
                The result is a ranked list of the most relevant functions across your codebase,
                with file paths and line numbers. Claude can then call smart_read on exactly
                those files rather than guessing.
              </p>

              <div className="mt-5 rounded-xl bg-stone-950 px-5 py-4 font-mono text-xs text-stone-400 space-y-1">
                <p className="text-stone-500 mb-2"># search_context(&quot;handle Slack notification failure&quot;)</p>
                <p><span className="text-indigo-400">integrations/slack.py</span>:84   function post_message</p>
                <p><span className="text-indigo-400">integrations/slack.py</span>:121  function post_approval_message</p>
                <p><span className="text-indigo-400">runtime/executor.py</span>:1192  function _execute_output</p>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">Why this matters at scale</h2>
              <p>
                On a small project, reading whole files is fine. On a codebase with 200 files
                and 15,000 functions, every unnecessary read compounds. An agentic session
                might read 30–50 files across a single task. Without smart_read, that&apos;s
                potentially millions of tokens — most of it irrelevant.
              </p>
              <p className="mt-4">
                Reuven Cohen&apos;s observation that swarm-style AI development costs ~$2,500/day
                is not a model pricing problem. It&apos;s an information flow problem. The same
                context — architecture docs, source files, conversation history — gets resent
                on every call. Smart_read is the fix at the file level.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-stone-900 mb-3">Try it</h2>
              <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-sm space-y-1">
                <p className="text-stone-500 text-xs mb-2"># install and index</p>
                <p className="text-emerald-400">pip install agent-booster</p>
                <p className="text-emerald-400">booster index</p>
                <p className="mt-3 text-stone-500 text-xs mb-2"># wire to Claude Code</p>
                <p className="text-emerald-400">booster init claude</p>
                <p className="mt-3 text-stone-500 text-xs mb-2"># see savings after a session</p>
                <p className="text-emerald-400">booster gain</p>
              </div>
              <p className="mt-5 text-sm text-stone-500">
                Add <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600 text-[13px]">--embed</code> to
                the index command to enable semantic search.
                Without it, Booster falls back to keyword matching — still useful, just less precise.
              </p>
            </section>

          </div>

          <hr className="border-stone-100 mt-12 mb-8" />
          <div className="flex items-center justify-between text-sm">
            <a href="/blog" className="text-stone-400 hover:text-stone-700 transition-colors">← All posts</a>
            <a
              href="/tools/agent-booster"
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
        <a href="/tools/agent-booster" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Agent Booster</a>
        <a href="/marketplace" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Playbooks</a>
        <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
      </div>
    </header>
  )
}
