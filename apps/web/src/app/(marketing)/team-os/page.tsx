"use client"

import { useState } from "react"
import { Check, Copy, Download, ArrowRight, FileText, Shield, Database } from "lucide-react"
import { CtaLink } from "@/components/marketing/CtaLink"

/* ─── Page ──────────────────────────────────────────────────────────────── */

export default function TeamOSPage() {
  return (
    <>
      <HeroSection />
      <LayerDiagramSection />
      <FilesSection />
      <StandardsSection />
      <AdoptionSection />
      <Layer2BridgeSection />
    </>
  )
}

/* ─── Hero ──────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="max-w-4xl mx-auto px-6 pt-20 pb-14 text-center">
      <div className="inline-flex items-center gap-2 bg-emerald-50 text-emerald-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
        Layer 0 — Free Forever
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        The operating system<br />
        <span className="bg-gradient-to-r from-emerald-600 to-teal-600 bg-clip-text text-transparent">for AI-assisted teams.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-4">
        Three files. Any stack. No account required.
      </p>
      <p className="text-base text-stone-600 max-w-2xl mx-auto leading-relaxed mb-8">
        Agents finish work to their standard, not yours — unless you write yours down.
        Team OS is the foundation layer: <code className="bg-stone-100 px-1.5 py-0.5 rounded text-sm font-mono">CLAUDE.md</code> gives agents your project memory,{" "}
        <code className="bg-stone-100 px-1.5 py-0.5 rounded text-sm font-mono">REVIEW.md</code> gives them your quality bar,
        and <code className="bg-stone-100 px-1.5 py-0.5 rounded text-sm font-mono">standards/</code> gives them your playbook.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a
          href="#files"
          className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center"
        >
          Get the templates
        </a>
        <a
          href="https://github.com/conductai/team-os"
          target="_blank"
          rel="noopener"
          className="rounded-xl border border-stone-300 bg-white text-stone-700 px-7 py-3.5 text-base font-semibold hover:border-stone-400 hover:shadow-sm transition-all w-full sm:w-auto text-center"
        >
          View on GitHub
        </a>
      </div>
      <p className="text-xs text-stone-400 mt-4">Free for individuals · commercial license for companies · Works with Claude Code, Cursor, Copilot, any AI coding tool</p>
    </section>
  )
}

/* ─── Layer Diagram ─────────────────────────────────────────────────────── */

function LayerDiagramSection() {
  return (
    <section className="bg-stone-950 border-y border-stone-800 py-12 px-6">
      <div className="max-w-4xl mx-auto">
        <p className="text-center text-[10px] font-semibold uppercase tracking-widest text-stone-500 mb-8">
          Two layers. Start at zero.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Layer 0 */}
          <div className="rounded-2xl border border-emerald-500/30 bg-emerald-950/30 p-6">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-2xl font-black text-emerald-400">Layer 0</span>
              <span className="text-xs bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded-full font-semibold">Free · Open source</span>
            </div>
            <p className="text-stone-300 text-sm mb-5 leading-relaxed">
              The MD files. Commit them to your repo. Agents read them before every task.
            </p>
            <div className="space-y-2 font-mono text-sm">
              <div className="flex items-center gap-2 text-stone-300">
                <FileText className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>CLAUDE.md <span className="text-stone-500">— project memory</span></span>
              </div>
              <div className="flex items-center gap-2 text-stone-300">
                <FileText className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>REVIEW.md <span className="text-stone-500">— quality gate</span></span>
              </div>
              <div className="flex items-center gap-2 text-stone-300">
                <FileText className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>standards/ <span className="text-stone-500">— the playbook</span></span>
              </div>
            </div>
          </div>

          {/* Layer 2 */}
          <div className="rounded-2xl border border-indigo-500/30 bg-indigo-950/30 p-6">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-2xl font-black text-indigo-400">Layer 2</span>
              <span className="text-xs bg-indigo-500/20 text-indigo-400 px-2 py-0.5 rounded-full font-semibold">Conduct AI</span>
            </div>
            <p className="text-stone-300 text-sm mb-5 leading-relaxed">
              Enforcement. When markdown alone isn&apos;t enough — real-time, auditable, team-wide.
            </p>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2 text-stone-300">
                <Shield className="w-4 h-4 text-indigo-400 shrink-0" />
                <span>Guard <span className="text-stone-500">— blocks before it runs</span></span>
              </div>
              <div className="flex items-center gap-2 text-stone-300">
                <Shield className="w-4 h-4 text-indigo-400 shrink-0" />
                <span>Security Loop <span className="text-stone-500">— scans every PR</span></span>
              </div>
              <div className="flex items-center gap-2 text-stone-300">
                <Shield className="w-4 h-4 text-indigo-400 shrink-0" />
                <span>Audit trail <span className="text-stone-500">— every AI action logged</span></span>
              </div>
            </div>
          </div>
        </div>
        <p className="text-center text-stone-500 text-sm mt-6">
          Layer 0 tells agents what to do.&nbsp;
          <span className="text-stone-300">Layer 2 makes sure they do it.</span>
        </p>
      </div>
    </section>
  )
}

/* ─── Files with copy buttons ───────────────────────────────────────────── */

const CLAUDE_MD_CONTENT = `# CLAUDE.md — [Your Project Name]

## About this project
{{ One paragraph: what this codebase does, who uses it, what problem it solves. }}

**Stack:** {{ e.g. FastAPI + PostgreSQL + Next.js + Redis }}

---

## Before starting any task

1. Read \`REVIEW.md\` — every task ends with this checklist
2. Check the relevant standard in \`standards/\` if your change touches auth, security, or the database
3. Run the test suite before and after: \`{{ your test command }}\`

---

## What agents should never do
- {{ e.g. Never mint tokens outside executor.py }}
- {{ e.g. Never push directly to the main branch }}
- {{ e.g. Never skip the downgrade() step in a migration }}

## The patterns we use
- **Auth:** {{ e.g. require_permission("platform.xyz") — not require_workspace_role() }}
- **DB queries:** {{ e.g. SQLAlchemy ORM, parameterised only — no f-string SQL }}
- **Logging:** {{ e.g. structlog with snake_case keys — no print() in production code }}

---

## Security rules (non-negotiable)
- Every API endpoint requires an auth dependency
- User input is never concatenated into SQL
- Secrets and tokens are never logged or returned in API responses

---

## CI gates (these must pass before merging)
\`\`\`bash
{{ your test command }}      # Tests — no || true
{{ your lint command }}      # Lint
{{ your typecheck command }} # Types
\`\`\`

---
<!-- Layer 0: Team OS · conductai.ai/team-os · Free for individuals, commercial license for companies -->
`

const REVIEW_MD_CONTENT = `# REVIEW.md — Quality Gate

Before any agent declares work done, every applicable item here must be checked.
Before any human opens a PR, run through this list.

## The standard
Done means: the next engineer reads this in 6 months with no questions.

---

## Pre-ship checklist

### Auth
- [ ] Every new endpoint has an auth dependency in its signature
- [ ] New endpoints use permission names, not hardcoded role strings
- [ ] Intentionally public endpoints are in the allowlist with a documented reason
- [ ] Auth coverage CI gate passes

### Tests
- [ ] Test suite passes — no \`|| true\`, no unexplained skips
- [ ] New logic has a test that fails if the logic breaks
- [ ] Mocks match the real interface they replace

### Security
- [ ] No user input concatenated into SQL
- [ ] File paths from user input are bounded to the project root
- [ ] No secrets in logs, error messages, or API responses

### Database
- [ ] One migration per change
- [ ] Migration tested locally before push
- [ ] \`downgrade()\` defined
- [ ] Destructive changes staged: stop writing first, then drop

### Impact — all layers, every change
- [ ] CLI / SDK — any command, config key, or output format changed?
- [ ] Frontend — any route, field name, or response shape changed?
- [ ] API — breaking change for existing callers?
- [ ] DB — migration needed?

### Self-review
- [ ] Read your diff as if reviewing a stranger's PR
- [ ] Delete everything added "just in case"
- [ ] Remove all debugging artifacts
- [ ] Every name describes what it does — no comment needed

---

## What machines should check (automate these)
| Check | Command |
|---|---|
| Auth coverage | \`python scripts/check_auth_coverage.py\` |
| Tests | \`pytest tests/ -x -q\` |
| Type check | \`npm run typecheck\` |
| Lint | \`npm run lint\` |

---

## Principle
The gate is the work. A PR that passes this list from a non-engineer is safe to merge.
A PR that skips it is unsafe regardless of who wrote it.

<!-- Layer 0: Team OS · conductai.ai/team-os · Free for individuals, commercial license for companies -->
`

const STANDARDS_AUTH_CONTENT = `# Standard: Auth and Access Control

Every API endpoint must authenticate the caller before doing any work.

## The rule
No exceptions by default. Public endpoints go in an explicit, CI-checked allowlist
with a documented reason.

## The pattern
Use your framework's dependency injection for auth:

\`\`\`python
# FastAPI
@router.get("/resource")
def get_resource(
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("resource.read")),
    db: Session = Depends(get_db),
):
    ...
\`\`\`

Use permission names, not role names. Hardcoding \`require_role("admin")\` couples
endpoints to your current role structure. Permissions decouple them.

## The allowlist pattern
Build a CI gate that scans every route and fails on undocumented public endpoints.
Each allowlist entry must say why it's public:

\`\`\`python
ALLOWLIST = {
    "routers/health.py::health",          # Load balancer health check
    "routers/github_webhook.py::webhook", # Auth via X-Hub-Signature-256
    "routers/oauth.py::metadata",         # Public by RFC 8414
}
\`\`\`

## What to check in review
- [ ] New endpoint has an auth dependency
- [ ] Uses permission names, not role strings
- [ ] If no auth: in the allowlist with a reason
- [ ] CI gate passes

<!-- Layer 0: Team OS · conductai.ai/team-os · Free for individuals, commercial license for companies -->
`

interface FileCardProps {
  filename: string
  description: string
  content: string
  icon: React.ReactNode
  color: string
}

function CopyButton({ content }: { content: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 text-xs font-medium text-stone-500 hover:text-stone-800 transition-colors"
    >
      {copied ? (
        <>
          <Check className="w-3.5 h-3.5 text-emerald-500" />
          <span className="text-emerald-600">Copied</span>
        </>
      ) : (
        <>
          <Copy className="w-3.5 h-3.5" />
          Copy
        </>
      )}
    </button>
  )
}

function FileCard({ filename, description, content, icon, color }: FileCardProps) {
  const [expanded, setExpanded] = useState(false)
  const preview = content.split("\n").slice(0, 12).join("\n")

  return (
    <div className="rounded-2xl border border-stone-200 bg-white overflow-hidden shadow-sm">
      <div className="flex items-start justify-between gap-4 px-6 py-5 border-b border-stone-100">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-lg ${color} flex items-center justify-center shrink-0`}>
            {icon}
          </div>
          <div>
            <h3 className="font-mono font-bold text-stone-900 text-sm">{filename}</h3>
            <p className="text-xs text-stone-500 mt-0.5">{description}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <CopyButton content={content} />
          <a
            href={`data:text/plain;charset=utf-8,${encodeURIComponent(content)}`}
            download={filename}
            className="flex items-center gap-1.5 text-xs font-medium text-stone-500 hover:text-stone-800 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Download
          </a>
        </div>
      </div>
      <div className="relative">
        <pre className={`text-xs text-stone-600 font-mono p-6 leading-relaxed overflow-x-auto bg-stone-50 ${!expanded ? "max-h-52 overflow-hidden" : ""}`}>
          {expanded ? content : preview}
        </pre>
        {!expanded && (
          <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-stone-50 to-transparent flex items-end justify-center pb-3">
            <button
              onClick={() => setExpanded(true)}
              className="text-xs font-semibold text-stone-500 hover:text-stone-800 transition-colors bg-stone-50 px-3 py-1 rounded-full border border-stone-200"
            >
              Show full file
            </button>
          </div>
        )}
        {expanded && (
          <div className="flex justify-center py-3 border-t border-stone-100">
            <button
              onClick={() => setExpanded(false)}
              className="text-xs font-semibold text-stone-500 hover:text-stone-800 transition-colors"
            >
              Collapse
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function FilesSection() {
  return (
    <section id="files" className="max-w-4xl mx-auto px-6 py-16">
      <div className="text-center mb-12">
        <h2 className="text-3xl font-black text-stone-900 mb-3">The three files</h2>
        <p className="text-stone-500 max-w-xl mx-auto">
          Copy each one into your repo, fill in the <code className="bg-stone-100 px-1 py-0.5 rounded text-xs font-mono">{`{{ }}`}</code> placeholders, commit.
          That&apos;s it.
        </p>
      </div>

      <div className="space-y-6">
        <FileCard
          filename="CLAUDE.md"
          description="Project memory — the context an agent needs before starting any task"
          content={CLAUDE_MD_CONTENT}
          icon={<FileText className="w-4 h-4 text-emerald-600" />}
          color="bg-emerald-50"
        />
        <FileCard
          filename="REVIEW.md"
          description="Quality gate — what 'done' means on your team, checked before every PR"
          content={REVIEW_MD_CONTENT}
          icon={<FileText className="w-4 h-4 text-violet-600" />}
          color="bg-violet-50"
        />
        <FileCard
          filename="standards/auth.md"
          description="Auth standard — the pattern, the allowlist, the CI gate"
          content={STANDARDS_AUTH_CONTENT}
          icon={<Shield className="w-4 h-4 text-blue-600" />}
          color="bg-blue-50"
        />
      </div>

      <div className="mt-6 flex flex-col items-center gap-1 text-center">
        <a
          href="https://github.com/conductai/team-os"
          target="_blank"
          rel="noopener"
          className="inline-flex items-center gap-2 text-sm text-stone-500 hover:text-stone-800 transition-colors"
        >
          Full standards library on GitHub
          <ArrowRight className="w-3.5 h-3.5" />
        </a>
        <p className="text-xs text-stone-400">
          Free for individuals · companies need a{" "}
          <a href="/team-os/license" className="underline underline-offset-2 hover:text-stone-600">commercial license</a>
        </p>
      </div>
    </section>
  )
}

/* ─── Standards preview ─────────────────────────────────────────────────── */

function StandardsSection() {
  const standards = [
    {
      icon: <Shield className="w-5 h-5 text-blue-600" />,
      bg: "bg-blue-50",
      title: "Auth",
      file: "standards/auth.md",
      lines: [
        "Pattern: framework dependency injection, not middleware",
        "Permission names, not role strings",
        "CI gate that scans every route",
        "Allowlist with documented reasons",
      ],
    },
    {
      icon: <Shield className="w-5 h-5 text-red-500" />,
      bg: "bg-red-50",
      title: "Security",
      file: "standards/security.md",
      lines: [
        "The 4 injection classes AI tools get wrong",
        "Parameterised queries, bounded file paths",
        "No secrets in defaults, logs, or responses",
        "CORS scope rules for authenticated endpoints",
      ],
    },
    {
      icon: <Database className="w-5 h-5 text-amber-600" />,
      bg: "bg-amber-50",
      title: "Migrations",
      file: "standards/migrations.md",
      lines: [
        "One change per migration",
        "Test locally before push",
        "downgrade() always defined",
        "Staged drops: stop writing first",
      ],
    },
  ]

  return (
    <section className="bg-stone-50 border-y border-stone-100 py-16 px-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-10">
          <h2 className="text-3xl font-black text-stone-900 mb-3">Standards library</h2>
          <p className="text-stone-500 max-w-xl mx-auto">
            Each standard covers one high-risk area — the pattern, the checklist, and the most common AI-generated mistake in that area.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {standards.map((s) => (
            <div key={s.title} className="bg-white rounded-2xl border border-stone-200 p-5">
              <div className="flex items-center gap-3 mb-4">
                <div className={`w-9 h-9 rounded-lg ${s.bg} flex items-center justify-center`}>
                  {s.icon}
                </div>
                <div>
                  <p className="font-bold text-stone-900 text-sm">{s.title}</p>
                  <p className="text-[10px] text-stone-400 font-mono">{s.file}</p>
                </div>
              </div>
              <ul className="space-y-1.5">
                {s.lines.map((line) => (
                  <li key={line} className="flex items-start gap-2 text-xs text-stone-600">
                    <span className="text-emerald-500 mt-0.5 shrink-0">✓</span>
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="text-center text-xs text-stone-400 mt-6">
          More standards (naming, testing, release) coming. Contributions welcome.
        </p>
      </div>
    </section>
  )
}

/* ─── Adoption timeline ─────────────────────────────────────────────────── */

function AdoptionSection() {
  const steps = [
    { week: "Week 1", action: "Commit the three files", result: "Agents have context and a quality bar" },
    { week: "Week 2", action: "Add to CLAUDE.md: check REVIEW.md before done", result: "Agents self-review before finishing" },
    { week: "Week 3", action: "Automate one CI gate", result: "Structure enforced without a reviewer's memory" },
    { week: "Week 4", action: "Retro: which items caught real bugs?", result: "Cut noise, add misses — bar improves" },
    { week: "Ongoing", action: "Production bug? Add the check that would have caught it", result: "Gate compounds over time" },
  ]

  return (
    <section className="max-w-4xl mx-auto px-6 py-16">
      <div className="text-center mb-10">
        <h2 className="text-3xl font-black text-stone-900 mb-3">Adopt it in a sprint</h2>
        <p className="text-stone-500 max-w-xl mx-auto">
          You don&apos;t need to implement everything at once. The progression builds naturally.
        </p>
      </div>
      <div className="space-y-3">
        {steps.map((step, i) => (
          <div key={i} className="flex items-start gap-4 rounded-xl border border-stone-200 bg-white px-5 py-4">
            <div className="w-16 shrink-0">
              <span className="text-xs font-bold text-stone-400 uppercase tracking-widest">{step.week}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-stone-800">{step.action}</p>
              <p className="text-xs text-stone-500 mt-0.5">{step.result}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ─── Bridge to Layer 2 ─────────────────────────────────────────────────── */

function Layer2BridgeSection() {
  return (
    <section className="bg-stone-950 border-t border-stone-800 py-16 px-6">
      <div className="max-w-4xl mx-auto text-center">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-stone-500 mb-6">When Layer 0 isn&apos;t enough</p>
        <h2 className="text-3xl font-black text-white mb-4">
          Layer 0 works on the honour system.
        </h2>
        <p className="text-stone-400 max-w-2xl mx-auto mb-8 leading-relaxed">
          Agents read the files and try to follow them. Humans check the PR. That handles one repo and one team.
          When you&apos;re managing multiple teams, need enforcement before code is written, and need a log that holds up in a security review — that&apos;s Layer 2.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10 text-left">
          {[
            { label: "Guard", desc: "Intercepts every AI tool call. Checks it against your standards before it runs. Blocks, warns, or allows — with a timestamped log." },
            { label: "Security Loop", desc: "Scans every PR for OWASP Top 10, secrets, and your custom rules. Critical findings trigger Autopilot to fix them." },
            { label: "Audit trail", desc: "Every AI action, every policy decision, every block. Attributable to agent, user, and workflow. Exportable for compliance." },
          ].map((item) => (
            <div key={item.label} className="rounded-xl border border-stone-800 bg-stone-900 p-5">
              <p className="font-bold text-white text-sm mb-2">{item.label}</p>
              <p className="text-stone-400 text-xs leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <CtaLink className="rounded-xl bg-white text-stone-900 px-7 py-3.5 text-base font-semibold hover:bg-stone-100 transition-colors w-full sm:w-auto text-center" />
          <a
            href="/guard"
            className="rounded-xl border border-stone-700 text-stone-300 px-7 py-3.5 text-base font-semibold hover:border-stone-500 hover:text-white transition-all w-full sm:w-auto text-center"
          >
            Learn about Guard
          </a>
        </div>
        <div className="mt-6 space-y-1 text-xs text-stone-600">
          <p>Free for individuals and teams under 10 people. Commercial use by larger organisations requires a license.</p>
          <p>
            <a href="/team-os/license" className="text-stone-400 hover:text-stone-300 underline underline-offset-2">View license</a>
            {" · "}
            <a href="mailto:hello@conductai.ai" className="text-stone-400 hover:text-stone-300 underline underline-offset-2">hello@conductai.ai</a>
          </p>
        </div>
      </div>
    </section>
  )
}
