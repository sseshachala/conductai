import { GitHubIcon } from "./shared"

/* ─── What's New ───────────────────────────────────────────────────────── */

const WHATS_NEW_ITEMS = [
  {
    icon: "🔑",
    title: "RFC 8693 token exchange",
    tag: "v0.7.28",
    desc: "conduct login now follows RFC 8693 — the same token exchange standard as Okta and Entra. The browser relays your Clerk session to the CLI, which exchanges it at POST /token for a cond_agt_* token. No custom auth flow to explain to your security team.",
    color: "text-indigo-600",
    bg: "bg-indigo-50 border-indigo-200",
  },
  {
    icon: "🪙",
    title: "Long-lived API tokens",
    tag: "v0.7.28",
    desc: "Create cond_api_* tokens from the Agent Identity page for CI/CD pipelines, server agents, and integrations. Same proxy enforcement and audit trail as session tokens, no expiry unless you revoke them.",
    color: "text-violet-600",
    bg: "bg-violet-50 border-violet-200",
  },
  {
    icon: "👁",
    title: "conduct token",
    tag: "v0.7.27",
    desc: "Reveals your current agent token. Tokens are masked in all sync output by default — run conduct token when you need the raw value for debugging or manual API calls.",
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
  },
  {
    icon: "⚡",
    title: "Proactive token refresh",
    tag: "v0.7.24",
    desc: "conduct guard sync checks token expiry and refreshes automatically 5 minutes before the 8-hour window closes. No interrupted sessions, no manual re-login during long coding runs.",
    color: "text-amber-600",
    bg: "bg-amber-50 border-amber-200",
  },
  {
    icon: "📡",
    title: "MCP Registry listing",
    tag: "v0.6.4 / v0.6.10",
    desc: "Both agent-booster and conduct-cli are now published to the official MCP Registry (registry.modelcontextprotocol.io). Install directly from VS Code, Cursor, or any MCP-compatible client without manual config.",
    color: "text-indigo-600",
    bg: "bg-indigo-50 border-indigo-200",
  },
  {
    icon: "🔀",
    title: "Call graph navigation",
    tag: "v0.6.4",
    desc: "expand_calls(symbol, direction) returns immediate callers or callees of any symbol. One MCP round-trip, cycle-safe depth up to 3, same-file resolution at index time, name-based cross-file resolution at query time. Stop re-searching for who calls what.",
    color: "text-violet-600",
    bg: "bg-violet-50 border-violet-200",
  },
  {
    icon: "📅",
    title: "Diff-aware reads",
    tag: "v0.6.4",
    desc: "Pass since='HEAD~5' or any git ref to smart_read or search_context. Returns only symbols whose lines changed in the range. Git context lives in the read now, no separate git diff parse, no whole-file scan to figure out what's new.",
    color: "text-amber-600",
    bg: "bg-amber-50 border-amber-200",
  },
  {
    icon: "✅",
    title: "Test signal in every read",
    tag: "v0.6.4",
    desc: "booster index --tests builds the symbol-to-test map. test_coverage('login') returns the test files that reference it. smart_read can surface the answer to 'is this code tested?' before the agent decides whether the change is safe.",
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
  },
  {
    icon: "🕐",
    title: "Last-modified header",
    tag: "v0.6.4",
    desc: "Every symbol in smart_read output now carries [last_modified: sha date] via batched git blame. One subprocess per file, max-timestamp commit per symbol range. Know whether code is hot or legacy without a separate look.",
    color: "text-rose-600",
    bg: "bg-rose-50 border-rose-200",
  },
  {
    icon: "🤝",
    title: "Shared team index",
    tag: "v0.6.3",
    desc: "booster index-push uploads your symbol index to the team workspace via the Guard sync channel. Teammates run booster index-pull (or just conduct guard sync) to merge it locally, no re-indexing the same repo twice. Uses the same auth as guard sync, zero new config.",
    color: "text-indigo-600",
    bg: "bg-indigo-50 border-indigo-200",
  },
  {
    icon: "🎓",
    title: "booster learn",
    tag: "v0.2.28",
    desc: "Mines your local read history and Guard failed run traces to extract patterns, hot files, files that resist smart_read, turn limit failures. Writes corrections directly to CLAUDE.md under a dedicted block. Run booster learn --dry-run to preview first.",
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
  },
  {
    icon: "🗜️",
    title: "SmartCrusher",
    tag: "v0.2.27",
    desc: "Compression pass on every smart_read and search_context result before it reaches the model. JSON arrays: keeps first 5 + last 3 entries, drops middle duplicates. Repeated lines: collapsed into '… N identical lines omitted'. Kicks in above 2KB, small results pass through untouched.",
    color: "text-rose-600",
    bg: "bg-rose-50 border-rose-200",
  },
  {
    icon: "⚡",
    title: "Cache alignment",
    tag: "v0.2.26",
    desc: "Tools are now returned alphabetically with deterministically sorted schema keys on every request. Anthropic users get free KV cache hits on the tools prefix, same tool list every session means the prefix is already cached. Auto-detected from ANTHROPIC_API_KEY, no config needed. booster gain shows cache alignment status.",
    color: "text-amber-600",
    bg: "bg-amber-50 border-amber-200",
  },
  {
    icon: "🛑",
    title: "Output token tracking",
    tag: "v0.2.25",
    desc: "booster-stop.py fires on every Claude Code session end and captures actual output tokens from the stop event. Stores baseline vs. actual in .booster/stats.db. booster gain now shows real savings, not estimates.",
    color: "text-rose-600",
    bg: "bg-rose-50 border-rose-200",
  },
  {
    icon: "🔇",
    title: "Verbosity modes",
    tag: "v0.2.24",
    desc: "booster verbosity lite|full|ultra injects a conciseness block into CLAUDE.md, AGENTS.md, .cursorrules, and .windsurfrules. booster verbosity off removes it. Cuts output token count by 30–75% across all AI coding tools.",
    color: "text-purple-600",
    bg: "bg-purple-50 border-purple-200",
  },
  {
    icon: "🗜️",
    title: "Memory compression",
    tag: "v0.2.24",
    desc: "booster compress rewrites every file in memory/ through claude-haiku to strip filler and cut token count by ~60%. booster compress --dry-run previews savings without writing. Keeps project memory lean as it grows.",
    color: "text-teal-600",
    bg: "bg-teal-50 border-teal-200",
  },
  {
    icon: "⚡",
    title: "Background daemon",
    tag: "v0.2.18",
    desc: "booster start launches a persistent Unix socket process that keeps the embedding model loaded. search_context drops from 2–3 s cold-start to ~50 ms. Daemon survives editor restarts, it's not tied to any terminal.",
    color: "text-amber-600",
    bg: "bg-amber-50 border-amber-200",
  },
  {
    icon: "◎",
    title: "File watcher",
    tag: "v0.2.17",
    desc: "watchdog monitors the project for writes. Changed files are re-indexed within 2 seconds of a save, no manual booster index during a coding session. Daemon handles this automatically.",
    color: "text-blue-600",
    bg: "bg-blue-50 border-blue-200",
  },
  {
    icon: "≋",
    title: "Delta indexing",
    tag: "v0.2.16",
    desc: "SHA-256 hash and mtime stored per file in the SQLite index. Full re-index skips unchanged files entirely. Large repos that took seconds now finish in milliseconds. Use --force to override.",
    color: "text-violet-600",
    bg: "bg-violet-50 border-violet-200",
  },
  {
    icon: "◈",
    title: "Asymmetric embeddings",
    tag: "v0.2.16",
    desc: "Index-time vectors use a passage: prefix; query-time vectors use query:. Follows the E5 paper's asymmetric retrieval approach. Retrieval accuracy improves meaningfully over symmetric embeddings, especially for short function names.",
    color: "text-indigo-600",
    bg: "bg-indigo-50 border-indigo-200",
  },
  {
    icon: "✦",
    title: "booster start does everything",
    tag: "v0.2.18",
    desc: "One command bootstraps the full stack: detects installed AI tools (Claude Code, Cursor, Windsurf, Codex), wires each one that isn't already wired, indexes the project, builds embeddings, and starts the daemon. On subsequent runs it just wakes the daemon.",
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
  },
]

export function WhatsNewSection() {
  return (
    <section className="px-6 py-20 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-center gap-3 mb-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest">What&apos;s new</p>
          <span className="text-[10px] font-bold bg-emerald-100 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full uppercase tracking-widest">
            v0.2.16 – v0.7.28
          </span>
        </div>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          SmartCrusher, cache alignment, booster learn, and shared team index.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-12">
          Four new releases. The result: booster cuts costs at every layer, elimination, compression, caching, and learning from every session,
          search is instant after the first run, and re-indexing costs nothing on unchanged files.
        </p>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {WHATS_NEW_ITEMS.map((item) => (
            <div key={item.title} className={`rounded-2xl border ${item.bg} px-6 py-6 flex flex-col gap-3`}>
              <div className="flex items-start justify-between gap-2">
                <span className={`text-2xl font-black ${item.color}`}>{item.icon}</span>
                <span className="text-[10px] font-semibold text-stone-400 bg-white border border-stone-200 px-2 py-0.5 rounded-full font-mono mt-1">
                  {item.tag}
                </span>
              </div>
              <p className="text-sm font-bold text-stone-900">{item.title}</p>
              <p className="text-xs text-stone-600 leading-relaxed">{item.desc}</p>
            </div>
          ))}

          {/* Changelog link card */}
          <div className="rounded-2xl border border-stone-200 bg-white px-6 py-6 flex flex-col gap-3 justify-between">
            <div>
              <p className="text-sm font-bold text-stone-900 mb-2">Full changelog</p>
              <p className="text-xs text-stone-500 leading-relaxed">
                Every commit, diff, and release note lives in the GitHub repo. PRs welcome.
              </p>
            </div>
            <a
              href="https://github.com/sseshachala/conduct-cli/commits/main/tools/booster"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors mt-2"
            >
              <GitHubIcon />
              View commits →
            </a>
          </div>
        </div>
      </div>
    </section>
  )
}
