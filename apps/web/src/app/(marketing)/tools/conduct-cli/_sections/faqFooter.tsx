"use client"

import { useState } from "react"
import { CopyButton, GitHubIcon } from "./shared"

/* ─── FAQ ──────────────────────────────────────────────────────────────── */

const FAQS = [
  {
    q: "What is an AST and why does it matter?",
    a: "AST stands for Abstract Syntax Tree, a structured representation of source code. Instead of treating code as raw text, we parse it into a tree of nodes: functions, classes, parameters, and their relationships. This lets us extract just the symbols relevant to a task (say, 3 functions out of 1,800 lines) rather than sending the entire file. We use tree-sitter to parse Python and TypeScript files.",
  },
  {
    q: "How does the symbol index work?",
    a: "When you run booster index (or booster start on first run), we walk every .py / .ts / .tsx / .js / .jsx file with tree-sitter, extract all function and class nodes, and store name, kind, file path, start/end line, and signature into .booster/symbols.db. Delta indexing skips unchanged files, each file's SHA-256 hash and mtime are stored, so only modified files are re-parsed. Use booster index --force to bypass the delta cache and re-index everything.",
  },
  {
    q: "How does semantic search work?",
    a: "When you run booster index --embed (or booster embed), we load each symbol's name + signature into the all-MiniLM-L6-v2 model from sentence-transformers, encode them into 384-dimensional vectors, L2-normalize them, and save the matrix to .booster/vectors.npy. At query time we encode the task description the same way and compute cosine similarity (a dot product since both sides are unit-normalized) to find the top-K matching symbols. If the vector files don't exist, search automatically falls back to keyword matching.",
  },
  {
    q: "What happens when Claude reads a file through Booster?",
    a: "The MCP smart_read tool receives the file path and a task description. It uses RRF (Reciprocal Rank Fusion) to merge two ranked lists, a vector similarity search and a keyword LIKE search, using the formula score = Σ 1/(60 + rank). This surfaces symbols that score well on either or both strategies, instead of relying on embeddings alone. The result is AST symbol slices (source lines for matching functions/classes) with a header showing name and line range. A 5 KB gate caps output, if matched symbols exceed 5 KB, only the top-3 RRF-ranked symbols are returned with a truncation notice. Every call is logged to .booster/stats.db so booster gain can report real token savings.",
  },
  {
    q: "How does token savings tracking work?",
    a: "Each smart_read call records three things in .booster/stats.db: the full file text size, the slice size returned, and the task description. Token count is estimated as len(text) // 4 (a standard rough approximation). booster gain reads this database and reports total tokens served vs. tokens that would have been sent without Booster, broken down by file.",
  },
  {
    q: "What does booster init actually change on my machine?",
    a: "For Claude Code, booster init claude writes six things: .mcp.json (registers the MCP server), CLAUDE.md (appends a rules block), .claude/settings.json (wires three hooks), and three hook scripts, booster-gate.py (blocks Read on indexed files and forces smart_read), booster-grep-nudge.py (detects semantic Grep patterns and suggests search_context instead), and booster-route.py (fires on every user message and recommends haiku/sonnet/opus before Claude starts work). Before writing anything, it prints a full list of changes and asks for confirmation. Run booster remove claude to undo everything cleanly. No residue.",
  },
  {
    q: "Does Booster send my code anywhere?",
    a: "No code, no prompts, no file content ever leaves your machine. The symbol index, vector store, and stats database are all local, stored in .booster/ inside your project. The MCP server runs as a local stdio process. No network calls, no telemetry, no structured events phoned home. The only external call is the one-time model download from HuggingFace when you first run booster embed.",
  },
  {
    q: "Does it work with TypeScript and other languages?",
    a: "Yes. Booster indexes Python (.py) and TypeScript/TSX/JS/JSX files. We use tree-sitter-python for Python and tree-sitter-typescript for TypeScript, extracting functions, classes, methods, interfaces, and named arrow functions. Build artifacts (.next/, dist/, build/) are automatically excluded from indexing so minified bundles never pollute the symbol index.",
  },
  {
    q: "How is this different from just using prompt caching?",
    a: "Prompt caching (Layer 1) reuses stable prefixes that have already been sent, it reduces cost on repeated context. Booster (Layer 3) prevents that context from being sent in the first place. A 1,800-line file cached still costs full price on the first read of a session. Booster routes only the relevant 80 lines every time, whether or not caching is active. The two stack: Booster reduces what you send, caching reduces the cost of what you sent previously.",
  },
  {
    q: "Does it work across multiple terminal sessions on the same machine?",
    a: "Yes. The hooks and MCP server are wired via .claude/settings.json and .mcp.json at the project root, not tied to any specific terminal window or session. Every Claude Code session you open inside the project directory (any terminal, same machine) automatically gets the Read gate, Grep nudge, and route_model hook. The MCP server starts fresh per session but the index is shared (it's just .booster/symbols.db on disk). The only requirement: run booster init claude once per project, not once per session.",
  },
  {
    q: "Does each developer on my team need to run booster init?",
    a: "Yes, once per developer, once per project. Each developer runs pip install 'agent-booster[full]' then booster start inside the project. booster start wires the AI tools it detects, indexes the codebase, builds embeddings, and starts the daemon, nothing manual. The symbol index is gitignored so each developer builds their own locally. For teams, ConductGuard fleet admin (coming) will push the setup automatically to every developer's workspace.",
  },
]

export function FaqSection() {
  const [open, setOpen] = useState<number | null>(null)

  return (
    <section className="px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Under the hood</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
          How it&apos;s actually built.
        </h2>

        <div className="flex flex-col divide-y divide-stone-100">
          {FAQS.map((faq, idx) => (
            <div key={idx} className="py-5">
              <button
                onClick={() => setOpen(open === idx ? null : idx)}
                className="w-full flex items-start justify-between gap-4 text-left"
              >
                <span className="text-sm font-semibold text-stone-900">{faq.q}</span>
                <span className="shrink-0 mt-0.5 text-stone-400 text-lg leading-none">
                  {open === idx ? "−" : "+"}
                </span>
              </button>
              {open === idx && (
                <p className="mt-3 text-sm text-stone-500 leading-relaxed">{faq.a}</p>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Footer CTA ───────────────────────────────────────────────────────── */

export function FooterCTASection() {
  return (
    <section className="px-6 py-20 text-center">
      <h2 className="text-3xl font-bold text-stone-900 mb-4">
        Your terminal. Your team&apos;s rules.{" "}
        <span className="text-indigo-600">One CLI.</span>
      </h2>
      <p className="text-stone-500 mb-8 max-w-lg mx-auto">
        Run agents, enforce policies, switch workspaces, and know exactly what context your
        terminal is operating in &mdash; all from a single command.
      </p>

      <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
        <div className="flex items-center rounded-xl bg-stone-950 px-5 py-3">
          <code className="font-mono text-sm text-emerald-400">pip install conduct-cli</code>
          <CopyButton text="pip install conduct-cli" />
        </div>
        <a
          href="https://github.com/sseshachala/conduct-cli"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          <GitHubIcon />
          View on GitHub
        </a>
      </div>
      <p className="mt-4 text-xs text-stone-400">Python 3.10+ · Free for individuals · commercial license for companies</p>
    </section>
  )
}

