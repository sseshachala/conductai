// Static hero composite for the launch blog post. Open at /blog/launch-hero,
// screenshot at full window height, save to /public/blog/launch-hero.png.
// All data is hard-coded — no API calls. Tweak numbers/names below.

export const metadata = {
  title: "Conduct launch hero",
}

const DEVELOPERS = [
  { email: "sudhi@b2bsphere.com",  tools: ["Claude", "Codex", "Cursor", "Claude.ai"], last: "3:56 AM" },
  { email: "alex@b2bsphere.com",   tools: ["Claude", "Cursor"],                       last: "3:42 AM" },
  { email: "maya@b2bsphere.com",   tools: ["Claude", "Codex", "Cursor"],              last: "3:51 AM" },
  { email: "jordan@b2bsphere.com", tools: ["Claude", "Claude.ai"],                    last: "3:18 AM" },
  { email: "priya@b2bsphere.com",  tools: ["Cursor", "Codex"],                        last: "3:55 AM" },
]

const TREND = [
  ["06-02", 110, 8], ["06-03", 165, 5],  ["06-04", 195, 12], ["06-05", 280, 60],
  ["06-06", 240, 18], ["06-07", 320, 20], ["06-08", 215, 4],  ["06-09", 305, 6],
  ["06-10", 240, 3],  ["06-11", 395, 0],  ["06-12", 320, 0],  ["06-13", 275, 2],
  ["06-14", 130, 0],  ["06-15", 0, 0],     ["06-16", 175, 0],  ["06-17", 170, 0],
  ["06-18", 320, 0],  ["06-19", 345, 0],  ["06-20", 470, 0],  ["06-21", 370, 0],
  ["06-22", 525, 0],  ["06-23", 460, 0],  ["06-24", 95, 0],
] as const

const EVENTS = [
  { time: "just now", user: "alex",   tool: "Claude Code", call: "bash",                 decision: "blocked", reason: "Production deploy require…", tokens: "214k in / 173 out" },
  { time: "2m ago",   user: "maya",   tool: "Claude Code", call: "bash",                 decision: "allowed", reason: null,                          tokens: "212k in / 2k out" },
  { time: "4m ago",   user: "sudhi",  tool: "workflow",    call: "__guard_implement_fix", decision: "blocked", reason: "github_issue payload",        tokens: "2k in" },
  { time: "5m ago",   user: "jordan", tool: "Claude Code", call: "bash",                 decision: "allowed", reason: null,                          tokens: "211k in / 256 out" },
  { time: "6m ago",   user: "priya",  tool: "Claude Code", call: "bash",                 decision: "allowed", reason: null,                          tokens: "208k in / 2k out" },
]

const GUARDRAILS = [
  ["Prompt caching",       "config"],
  ["Model routing",        "config"],
  ["Prompt splitting",     "config"],
  ["Deterministic offload","auto"],
  ["Output compression",   "auto"],
  ["Structured retrieval", "auto"],
  ["Metrics & budgets",    "auto"],
]

const Stat = ({ value, label, sub, color = "text-stone-900" }: { value: string; label: string; sub?: string; color?: string }) => (
  <div className="bg-white rounded-2xl border border-stone-200 px-6 py-5 shadow-sm">
    <div className={`text-4xl font-bold ${color}`}>{value}</div>
    <div className="mt-3 text-[10px] font-semibold uppercase tracking-widest text-stone-400">{label}</div>
    {sub && <div className="text-xs text-stone-500 mt-1">{sub}</div>}
  </div>
)

const maxBar = Math.max(...TREND.map(d => Number(d[1]) + Number(d[2])))

export default function LaunchHero() {
  return (
    <div className="bg-stone-50 min-h-screen px-8 py-10 font-sans">
      <div className="max-w-[1400px] mx-auto flex flex-col gap-8">

        {/* ─── Panel 1: Overview KPIs ─────────────────────────────── */}
        <section className="bg-stone-50">
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-2xl font-bold text-stone-900">Guard</h2>
            <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full">● live</span>
            <span className="text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-full">● Standard · 39 rules</span>
            <span className="ml-auto text-xs text-stone-400">last updated: 1m ago</span>
          </div>
          <p className="text-sm text-stone-500 mb-6 max-w-3xl">
            MDM for AI coding tools. When a hard cap is hit, every tool call across Claude Code, Codex, and Cursor is blocked immediately and your security team is notified on Slack.
          </p>

          <div className="grid grid-cols-6 gap-4">
            <Stat value="5"      label="Active developers" sub="developers active" color="text-emerald-700" />
            <Stat value="12,847" label="Events today"      sub="tool calls logged" />
            <Stat value="87"     label="Blocked today"     sub="click to filter"  color="text-red-600" />
            <Stat value="142.6M" label="Tokens saved"      sub="vs unguarded calls" color="text-indigo-700" />
            <Stat value="68.4M tokens" label="Est. savings" sub="$1,247.92 saved"    color="text-indigo-700" />
            <Stat value="Clean"  label="Token efficiency" sub="no waste detected"  color="text-emerald-700" />
          </div>

          <div className="mt-6 grid grid-cols-6 gap-4">
            <div className="bg-white rounded-2xl border border-stone-200 px-6 py-5 shadow-sm col-span-1">
              <div className="text-3xl font-bold text-emerald-700">5/5</div>
              <div className="mt-2 text-[10px] font-semibold uppercase tracking-widest text-stone-400">Tool coverage</div>
              <div className="text-xs text-stone-500 mt-1">5 devs · all covered</div>
            </div>

            <div className="bg-white rounded-2xl border border-stone-200 px-6 py-5 shadow-sm col-span-5">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-stone-400 mb-3">Tool coverage — 6/24/2026</div>
              <div className="flex flex-col gap-2.5">
                {DEVELOPERS.map(d => (
                  <div key={d.email} className="flex items-center gap-3 text-sm">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                    <span className="text-stone-700 font-medium w-56 truncate">{d.email}</span>
                    <div className="flex gap-2 flex-1">
                      {d.tools.map(t => (
                        <span key={t} className="text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">✓ {t}</span>
                      ))}
                    </div>
                    <span className="text-xs text-stone-400">6/24/2026, {d.last}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ─── Panel 2: Guardrails + cost trend ──────────────────── */}
        <section className="bg-white rounded-2xl border border-stone-200 shadow-sm">
          <div className="px-7 py-5 border-b border-stone-100 flex items-center justify-between">
            <div className="text-[10px] font-semibold uppercase tracking-widest text-stone-400">Token abuse guardrails</div>
            <div className="text-sm font-semibold text-emerald-700">7/7 active</div>
          </div>
          <div className="grid grid-cols-7 gap-4 px-7 py-6">
            {GUARDRAILS.map(([name, mode]) => (
              <div key={name} className="flex flex-col items-center text-center gap-2">
                <div className="w-12 h-12 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-700 text-xl">✓</div>
                <div className="text-sm font-medium text-stone-700">{name}</div>
                <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full ${mode === "config" ? "text-indigo-700 bg-indigo-50 border border-indigo-200" : "text-stone-500 bg-stone-100 border border-stone-200"}`}>{mode}</span>
              </div>
            ))}
          </div>

          <div className="px-7 py-6 border-t border-stone-100">
            <div className="flex items-center justify-between mb-5">
              <div className="text-base font-semibold text-stone-900">Est. cost trend</div>
              <div className="flex items-center gap-1 text-xs font-medium">
                <span className="px-3 py-1 rounded-md bg-stone-900 text-white">Daily</span>
                <span className="px-3 py-1 rounded-md text-stone-500">Weekly</span>
                <span className="px-3 py-1 rounded-md text-stone-500">Monthly</span>
              </div>
            </div>
            <div className="h-56 flex flex-col">
              <div className="flex-1 flex items-end gap-2">
                {TREND.map(([day, claude, codex]) => {
                  const c = Number(claude); const x = Number(codex)
                  const hClaude = (c / maxBar) * 100
                  const hCodex  = (x / maxBar) * 100
                  return (
                    <div key={day} className="flex-1 h-full flex flex-col-reverse">
                      <div style={{ height: `${hClaude}%`, background: "#4f46e5", borderRadius: "3px 3px 0 0" }} />
                      <div style={{ height: `${hCodex}%`,  background: "#0f766e", borderRadius: "3px 3px 0 0" }} />
                    </div>
                  )
                })}
              </div>
              <div className="flex gap-2 mt-2">
                {TREND.map(([day]) => (
                  <div key={String(day)} className="flex-1 text-[10px] text-stone-400 font-mono text-center">{day}</div>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-center gap-6 mt-4 text-xs text-stone-500">
              <span className="flex items-center gap-2"><span className="w-3 h-3 rounded-sm" style={{ background: "#4f46e5" }} /> Claude</span>
              <span className="flex items-center gap-2"><span className="w-3 h-3 rounded-sm" style={{ background: "#0f766e" }} /> Codex</span>
            </div>
          </div>
        </section>

        {/* ─── Panel 3: By AI tool + recent events ───────────────── */}
        <section className="bg-white rounded-2xl border border-stone-200 shadow-sm overflow-hidden">
          <div className="px-7 py-4 border-b border-stone-100">
            <div className="text-base font-semibold text-stone-900">By AI tool</div>
          </div>
          <div className="grid grid-cols-[1.4fr_1fr_1fr_1fr_1.6fr] gap-4 px-7 py-3 bg-stone-50 border-b border-stone-100 text-[10px] font-semibold uppercase tracking-widest text-stone-400">
            <div>Tool</div><div>Tokens used</div><div>Est. cost</div><div>Saved</div><div>% of total</div>
          </div>
          {[
            { tool: "claude_code", used: "56k", cost: "$30.8596", saved: "10.4M", pct: 100 },
            { tool: "workflow",    used: "0",   cost: "$0.0000",   saved: "13k",   pct: 0   },
            { tool: "platform",    used: "0",   cost: "$0.0000",   saved: "—",     pct: 0   },
          ].map(r => (
            <div key={r.tool} className="grid grid-cols-[1.4fr_1fr_1fr_1fr_1.6fr] gap-4 px-7 py-3 border-b border-stone-100 items-center text-sm">
              <div className="font-mono font-semibold text-stone-900">{r.tool}</div>
              <div className="font-mono text-stone-600">{r.used}</div>
              <div className="font-mono text-stone-600">{r.cost}</div>
              <div className="font-mono text-emerald-700">{r.saved}</div>
              <div className="flex items-center gap-3">
                <div className="flex-1 h-2 rounded-full bg-stone-200 overflow-hidden">
                  <div style={{ width: `${r.pct}%`, height: "100%", background: "#4f46e5" }} />
                </div>
                <span className="font-mono text-xs text-stone-400 w-9 text-right">{r.pct}%</span>
              </div>
            </div>
          ))}

          <div className="grid grid-cols-[100px_180px_140px_220px_1fr_140px_140px] gap-4 px-7 py-3 mt-2 bg-stone-50 border-y border-stone-100 text-[10px] font-semibold uppercase tracking-widest text-stone-400">
            <div>Time</div><div>User</div><div>AI tool</div><div>Call</div><div>Input</div><div>Decision</div><div>Tokens</div>
          </div>
          {EVENTS.map((e, i) => (
            <div key={i} className={`grid grid-cols-[100px_180px_140px_220px_1fr_140px_140px] gap-4 px-7 py-3 border-b border-stone-100 items-center text-sm ${e.decision === "blocked" ? "bg-red-50/40" : ""}`}>
              <div className="text-stone-400 text-xs">{e.time}</div>
              <div className="font-medium text-stone-700">{e.user}<div className="text-[10px] text-stone-400">{e.user}@b2bsphere.com</div></div>
              <div><span className={`text-xs font-medium px-2.5 py-1 rounded-full ${e.tool === "workflow" ? "bg-stone-100 text-stone-600" : "bg-indigo-50 text-indigo-700"}`}>{e.tool}</span></div>
              <div className="font-mono text-stone-700 text-xs">{e.call}</div>
              <div className="font-mono text-stone-500 text-xs truncate">{e.tool === "workflow" ? '{"github_issue": {"url": "https://gi…' : '{"command": "cd \\"/Users/sudhiseshac…'}</div>
              <div>
                <div className={`text-xs font-semibold ${e.decision === "blocked" ? "text-red-600" : "text-emerald-600"}`}>{e.decision === "blocked" ? "blocked" : "● "}</div>
                {e.reason && <div className="text-[10px] text-stone-400">{e.reason}</div>}
              </div>
              <div className="font-mono text-stone-700 text-xs text-right">{e.tokens}</div>
            </div>
          ))}
        </section>

      </div>
    </div>
  )
}
