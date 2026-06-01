"use client"

import { useRouter } from "next/navigation"
import { SignInButton, useAuth } from "@clerk/nextjs"

export default function GuardLandingPage() {
  return <GuardLanding />
}

function GuardLandingWithAuth() {
  const { isSignedIn, isLoaded } = useAuth()
  return <GuardLandingContent isSignedIn={!!isSignedIn} isLoaded={isLoaded} />
}

function GuardLanding() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <GuardLandingWithAuth />
  return <GuardLandingContent isSignedIn={false} isLoaded={true} />
}

function GuardLandingContent({ isSignedIn, isLoaded }: { isSignedIn: boolean; isLoaded: boolean }) {
  const router = useRouter()
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

  return (
    <div className="min-h-screen bg-white flex flex-col">

      {/* Nav */}
      <header className="px-6 py-5 flex items-center justify-between max-w-6xl mx-auto w-full">
        <div className="flex items-center">
          <a href="/">
            <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
          </a>
        </div>
        <div className="flex items-center gap-4">
          <a
            href="/"
            className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
          >
            Home
          </a>
          <a
            href="/guard"
            className="flex items-center gap-1.5 text-sm font-medium text-violet-700 hover:text-violet-900 transition-colors font-semibold"
          >
            Guard
          </a>
          <a
            href="/marketplace"
            className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
          >
            Playbooks
          </a>
          <a
            href="/docs"
            className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
          >
            Docs
          </a>
          <a
            href="https://cal.com/conductai/demo"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium bg-violet-700 hover:bg-violet-800 text-white px-4 py-2 rounded-lg transition-colors"
          >
            Book a demo
          </a>
          {isLoaded && (
            isSignedIn ? (
              <button
                onClick={() => router.push("/guard")}
                className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
              >
                Open app →
              </button>
            ) : clerkEnabled ? (
              <SignInButton mode="modal">
                <button className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
                  Sign in →
                </button>
              </SignInButton>
            ) : null
          )}
        </div>
      </header>

      {/* Hero — dark */}
      <section className="bg-stone-900 px-6 py-24 text-center">
        <div className="max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 bg-violet-900 text-violet-300 text-xs font-semibold px-3 py-1.5 rounded-full mb-8 uppercase tracking-wider">
            <span className="w-1.5 h-1.5 rounded-full bg-violet-400 inline-block" />
            ConductGuard — AI Governance for Engineering Teams
          </div>

          <h1 className="text-5xl sm:text-6xl font-bold text-white leading-[1.1] tracking-tight mb-6">
            Every AI tool.<br />Every developer.<br />
            <span className="text-violet-400">One policy.</span>
          </h1>

          <p className="text-xl text-stone-400 max-w-3xl mx-auto leading-relaxed mb-10">
            AI spend is now a board-level concern. Guard gives your VP Eng and CFO spend visibility,
            policy enforcement, and a full audit trail — across Claude Code, Cursor, Windsurf, and
            every other AI tool your team uses.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-10">
            <a
              href="/guard"
              className="inline-flex items-center gap-2 bg-violet-700 hover:bg-violet-800 text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors shadow-sm"
            >
              Set up Guard free →
            </a>
            <a
              href="https://cal.com/conductai/demo"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 border border-stone-600 hover:border-stone-400 text-stone-300 hover:text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors"
            >
              Book a demo →
            </a>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-3">
            {[
              "Works with 5+ AI coding tools",
              "BLOCK / WARN / AUDIT enforcement",
              "Real-time spend per developer",
            ].map(pill => (
              <span key={pill} className="text-xs font-medium text-stone-400 bg-stone-800 border border-stone-700 px-4 py-2 rounded-full">
                {pill}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Problem section — white */}
      <section className="px-6 py-20 bg-white">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-red-500 uppercase tracking-widest text-center mb-4">The problem</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
            Your team is spending thousands on AI tools.<br />You have no idea how.
          </h2>
          <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12 leading-relaxed">
            Every developer on your team is using AI coding tools. The bills arrive. The details don&apos;t.
          </p>

          <div className="grid sm:grid-cols-3 gap-6">
            {[
              {
                icon: "👁️",
                title: "No visibility",
                body: "Which developer spent £800 on Claude last month? Which project burned your budget? Today, you can't answer these questions.",
                accent: "border-red-200 bg-red-50",
                iconBg: "bg-red-100 text-red-600",
              },
              {
                icon: "🚫",
                title: "No policy",
                body: "Developers run rm -rf in production environments, push secrets to AI context, deploy to prod without review. Uncontrolled.",
                accent: "border-orange-200 bg-orange-50",
                iconBg: "bg-orange-100 text-orange-600",
              },
              {
                icon: "📋",
                title: "No audit",
                body: "When something goes wrong, there's no record of what the AI did, what was approved, or who authorised it.",
                accent: "border-amber-200 bg-amber-50",
                iconBg: "bg-amber-100 text-amber-600",
              },
            ].map(({ icon, title, body, accent, iconBg }) => (
              <div key={title} className={`rounded-2xl border ${accent} p-6 flex flex-col gap-4`}>
                <span className={`w-10 h-10 rounded-xl flex items-center justify-center text-xl ${iconBg}`}>{icon}</span>
                <div>
                  <p className="font-bold text-stone-900 mb-2">{title}</p>
                  <p className="text-sm text-stone-600 leading-relaxed">{body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works — stone-50 */}
      <section className="px-6 py-20 bg-stone-50">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-violet-600 uppercase tracking-widest text-center mb-4">How Guard works</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
            Set once. Enforced everywhere.
          </h2>
          <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12 leading-relaxed">
            Three steps. One team lead. Every developer covered.
          </p>

          <div className="grid sm:grid-cols-3 gap-6">
            {[
              {
                step: "1",
                icon: "🛡️",
                title: "Team lead sets policy",
                body: "Define spend caps, blocked commands, approved tool list, and enforcement mode — BLOCK, WARN, or AUDIT. One config, applied automatically to every developer on the team.",
              },
              {
                step: "2",
                icon: "⚡",
                title: "conduct guard join on each dev's machine",
                body: "Installs the PreToolUse hook in 30 seconds. No IT ticket. No manual configuration. Policies are downloaded and applied automatically.",
                code: "conduct guard join",
              },
              {
                step: "3",
                icon: "🔌",
                title: "MCP connects to every editor",
                body: "conductguard-mcp plugs Guard into Claude Code, Cursor, Windsurf, Aider, and Cline automatically. Policies enforced where AI actually runs.",
                code: "conductguard-mcp --team <id> --token <tok>",
              },
            ].map(s => (
              <div key={s.step} className="bg-white rounded-2xl border border-stone-200 p-6 flex flex-col gap-4">
                <div className="flex items-center gap-3">
                  <span className="w-7 h-7 rounded-full bg-violet-100 text-violet-700 text-xs font-bold flex items-center justify-center shrink-0">{s.step}</span>
                  <span className="text-xl">{s.icon}</span>
                </div>
                <div>
                  <p className="font-semibold text-stone-900 mb-2">{s.title}</p>
                  <p className="text-sm text-stone-500 leading-relaxed">{s.body}</p>
                </div>
                {s.code && (
                  <code className="text-xs bg-stone-900 text-emerald-400 px-3 py-2 rounded-lg font-mono mt-auto break-all">{s.code}</code>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Policy categories — white */}
      <section className="px-6 py-20 bg-white">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-4">What Guard enforces</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
            Policies your security team will recognise.
          </h2>
          <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12 leading-relaxed">
            Guard&apos;s policy categories map directly to the controls your InfoSec and compliance teams already care about.
          </p>

          <div className="grid sm:grid-cols-2 gap-5">
            {[
              {
                icon: "💥",
                title: "Destructive Operations",
                examples: ["rm -rf", "DROP TABLE", "kubectl delete"],
                enforcement: "BLOCK by default",
                enforcementColor: "bg-red-50 text-red-700 border-red-100",
                accent: "border-red-200",
                body: "Any AI-suggested command that could irrecoverably delete data, infrastructure, or configuration is blocked before it reaches the tool.",
              },
              {
                icon: "🔑",
                title: "Secrets & Credentials",
                examples: ["AWS keys", ".env files", "private tokens in AI context"],
                enforcement: "BLOCK by default",
                enforcementColor: "bg-red-50 text-red-700 border-red-100",
                accent: "border-red-200",
                body: "Guard detects when secrets are about to be sent to an AI model and blocks the call. Credentials never leave your machine via AI context.",
              },
              {
                icon: "🚀",
                title: "Production Gates",
                examples: ["deploy to prod", "terraform destroy", "vercel --prod"],
                enforcement: "APPROVAL required",
                enforcementColor: "bg-amber-50 text-amber-700 border-amber-100",
                accent: "border-amber-200",
                body: "Production deployments and irreversible infrastructure changes require explicit human approval — even when triggered by an AI workflow.",
              },
              {
                icon: "💸",
                title: "Spend Controls",
                examples: ["per-developer hard caps", "alert thresholds", "daily/monthly limits"],
                enforcement: "AUDIT + alert",
                enforcementColor: "bg-violet-50 text-violet-700 border-violet-100",
                accent: "border-violet-200",
                body: "Hard caps per developer per month. When a developer hits their limit, the next AI call is blocked at the source — not just flagged after the fact.",
              },
            ].map(({ icon, title, examples, enforcement, enforcementColor, accent, body }) => (
              <div key={title} className={`rounded-2xl border ${accent} p-6 flex flex-col gap-4`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{icon}</span>
                    <p className="font-bold text-stone-900">{title}</p>
                  </div>
                  <span className={`text-[10px] font-bold uppercase tracking-wider border px-2 py-0.5 rounded-full shrink-0 ${enforcementColor}`}>{enforcement}</span>
                </div>
                <p className="text-sm text-stone-500 leading-relaxed">{body}</p>
                <div className="flex flex-wrap gap-2">
                  {examples.map(ex => (
                    <code key={ex} className="text-xs bg-stone-100 text-stone-600 px-2 py-1 rounded font-mono">{ex}</code>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Three audit lenses — stone-50 */}
      <section className="px-6 py-20 bg-stone-50">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-4">Audit</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
            Three lenses. One audit trail.
          </h2>
          <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-12 leading-relaxed">
            A guard_check in a run trace links directly to the Guard audit entry — same moment, two lenses.
          </p>

          <div className="grid sm:grid-cols-3 gap-5 mb-8">
            {[
              {
                icon: "🛡️",
                label: "Guard audit",
                tag: "Every AI tool call",
                accent: "from-red-50 to-white border-red-200",
                iconBg: "bg-red-100 text-red-600",
                tagColor: "text-red-600",
                points: [
                  "Every Claude Code, Cursor, and AI tool call logged",
                  "Decision: allowed / blocked / warned",
                  "Which policy rule triggered and why",
                  "Tokens and cost per call, per developer",
                  "Slack alert in real time on block",
                ],
              },
              {
                icon: "🔁",
                label: "Run trace",
                tag: "Per workflow run",
                accent: "from-indigo-50 to-white border-indigo-200",
                iconBg: "bg-indigo-100 text-indigo-600",
                tagColor: "text-indigo-600",
                points: [
                  "Every block: started → completed → failed",
                  "Every LLM call and tool call inline",
                  "Guard policy check result in the trace",
                  "Live via Server-Sent Events while running",
                  "Immutable — append-only, never deleted",
                ],
              },
              {
                icon: "🏢",
                label: "Workspace events",
                tag: "Platform actions",
                accent: "from-violet-50 to-white border-violet-200",
                iconBg: "bg-violet-100 text-violet-600",
                tagColor: "text-violet-600",
                points: [
                  "Credential added, rotated, or removed",
                  "Agent installed or deleted",
                  "Member invited or role changed",
                  "Environment created or reassigned",
                  "Scoped to workspace",
                ],
              },
            ].map(({ icon, label, tag, accent, iconBg, tagColor, points }) => (
              <div key={label} className={`rounded-2xl border bg-gradient-to-br ${accent} p-6 flex flex-col gap-4`}>
                <div className="flex items-center justify-between">
                  <span className={`w-10 h-10 rounded-xl flex items-center justify-center text-xl ${iconBg}`}>{icon}</span>
                  <span className={`text-[10px] font-semibold uppercase tracking-wider ${tagColor}`}>{tag}</span>
                </div>
                <p className="font-bold text-stone-900">{label}</p>
                <ul className="space-y-1.5 flex-1">
                  {points.map(p => (
                    <li key={p} className="flex items-start gap-2 text-xs text-stone-500">
                      <span className="text-stone-300 mt-0.5 shrink-0">·</span>
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="rounded-2xl bg-white border border-stone-200 px-8 py-5 flex flex-col sm:flex-row items-center gap-5">
            <div className="text-2xl shrink-0">🔗</div>
            <p className="text-sm text-stone-500 leading-relaxed">
              A <code className="font-mono bg-stone-100 px-1 rounded">guard_check</code> in a run trace links directly to the Guard audit entry —
              same moment, two lenses. Rules evaluated, verdict, warnings — alongside the other block events.
            </p>
          </div>
        </div>
      </section>

      {/* Works with — white */}
      <section className="px-6 py-16 bg-white">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-2xl font-bold text-stone-900 mb-4">
            Works with the tools your team already uses.
          </h2>
          <p className="text-stone-500 text-sm mb-8">No rip-and-replace. Guard wraps around your existing AI tool stack.</p>
          <div className="flex flex-wrap items-center justify-center gap-3 mb-6">
            {["Claude Code", "Cursor", "Windsurf", "Aider", "Cline", "GitHub", "Slack"].map(tool => (
              <span key={tool} className="text-sm font-medium text-stone-600 bg-white border border-stone-200 px-4 py-2 rounded-full hover:border-stone-300 transition-colors">
                {tool}
              </span>
            ))}
          </div>
          <p className="text-xs text-stone-400">More integrations via MCP</p>
        </div>
      </section>

      {/* CTA section — violet */}
      <section className="bg-violet-700 px-6 py-20 text-center">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-3xl font-bold text-white mb-4">
            Start governing your team&apos;s AI usage today.
          </h2>
          <p className="text-violet-200 text-sm mb-10 leading-relaxed">
            Free during early access. No credit card. Set up in under 5 minutes.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <a
              href="/guard"
              className="inline-flex items-center gap-2 bg-white text-violet-700 hover:bg-violet-50 font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors shadow-sm"
            >
              Set up Guard →
            </a>
            <a
              href="https://cal.com/conductai/demo"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 border border-violet-400 hover:border-white text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors"
            >
              Book a demo →
            </a>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-stone-100 py-8 text-center text-xs text-stone-400">
        <div className="flex items-center justify-center gap-3 flex-wrap">
          <a href="/">
            <img src="/logo.png" alt="Conduct AI" className="h-6 w-auto inline-block" />
          </a>
          <span>·</span>
          <span>© {new Date().getFullYear()} Conduct</span>
          <span>·</span>
          <a href="/" className="hover:text-stone-600 transition-colors">Home</a>
          <span>·</span>
          <a href="/docs" className="hover:text-stone-600 transition-colors">Docs</a>
          <span>·</span>
          <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="hover:text-stone-600 transition-colors">GitHub</a>
          <span>·</span>
          <a href="/privacy" className="hover:text-stone-600 transition-colors">Privacy</a>
        </div>
      </footer>

    </div>
  )
}
