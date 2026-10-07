import Link from "next/link"
import { Code, Pre, SectionHeading, SubHeading } from "./shared"

export function GuardReferenceSections() {
  return (
    <>
      <section id="guard-token-savings">
        <SectionHeading id="guard-token-savings">RTK + Agent Booster</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Guard controls what your team <em>spends</em>. RTK and Agent Booster control what your team <em>burns</em>.
          Together they cut the token footprint of every Claude Code, Cursor, and Codex session, and Guard surfaces the combined savings on the dashboard automatically.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          <div className="rounded-xl border border-stone-200 px-5 py-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-bold px-2 py-0.5 rounded bg-stone-900 text-white font-mono">RTK</span>
              <span className="text-xs text-stone-400">Rust Token Killer</span>
            </div>
            <p className="text-sm text-stone-600 leading-relaxed mb-3">
              Wraps every CLI tool your agent calls — <Code>git</Code>, <Code>pytest</Code>, <Code>tsc</Code>, <Code>docker</Code>, and strips noise before the output reaches the model. Typical savings: <strong>60–99%</strong> per command.
            </p>
            <Pre>{`pip install rtk\nrtk git status   # 80% fewer tokens\nrtk pytest       # failures only, 90% savings`}</Pre>
          </div>
          <div className="rounded-xl border border-stone-200 px-5 py-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-bold px-2 py-0.5 rounded bg-indigo-600 text-white font-mono">Booster</span>
              <span className="text-xs text-stone-400">Agent Booster</span>
            </div>
            <p className="text-sm text-stone-600 leading-relaxed mb-3">
              Indexes your codebase with AST + vector embeddings. Intercepts raw file reads and grep calls, returning only the relevant symbol slices. Typical savings: <strong>60–70%</strong> per read. Hooks are active immediately after install, no session restart needed.
            </p>
            <Pre>{`pip install agent-booster\nbooster init claude   # indexes repo + wires hooks`}</Pre>
          </div>
        </div>

        <SubHeading>Real numbers from a single developer install</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Tool</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Tokens saved</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Savings %</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Est. cost saved</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["RTK",          "34.5M",  "99.2%", "$103.53"],
                ["Agent Booster","96.3K",  "62.5%", "—"],
              ].map(([tool, tokens, pct, cost]) => (
                <tr key={tool}>
                  <td className="px-4 py-3 font-mono text-xs font-semibold text-stone-800">{tool}</td>
                  <td className="px-4 py-3 text-stone-700 font-medium">{tokens}</td>
                  <td className="px-4 py-3"><span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">{pct}</span></td>
                  <td className="px-4 py-3 text-stone-700">{cost}</td>
                </tr>
              ))}
              <tr className="bg-stone-50">
                <td className="px-4 py-3 font-semibold text-stone-900">Combined</td>
                <td className="px-4 py-3 font-bold text-emerald-700">34.6M</td>
                <td className="px-4 py-3"><span className="text-xs font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">~99%</span></td>
                <td className="px-4 py-3 font-bold text-emerald-700">$103.53</td>
              </tr>
            </tbody>
          </table>
          <div className="border-t border-stone-100 px-4 py-2 bg-stone-50">
            <p className="text-xs text-stone-400">Measured over 1 day · 3,354 RTK commands · 30 Booster reads · Claude Sonnet pricing ($3.00/M tokens)</p>
          </div>
        </div>

        <SubHeading>How Guard surfaces savings</SubHeading>
        <p className="text-sm text-stone-600 leading-relaxed mb-4">
          At session end the <Code>booster-stop.py</Code> Stop hook automatically records actual output tokens (input savings come from the Read/Grep intercept hooks). When a developer runs <Code>conduct guard sync</Code>, the CLI reads <Code>rtk gain</Code> and <Code>booster gain</Code> and posts the totals to the Guard API. The <strong>Est. savings</strong> card on the Guard Spend dashboard shows the combined RTK + Booster delta per developer, no extra setup required.
        </p>
        <Pre>{`conduct guard sync\n\n#   Policy refreshed: 19 rule(s)\n#   Hook script updated\n#   Savings reported`}</Pre>

        <div className="mt-8 rounded-xl bg-indigo-50 border border-indigo-200 px-6 py-5 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex-1">
            <p className="font-semibold text-indigo-900 mb-1">Add Agent Booster to your workflow</p>
            <p className="text-sm text-indigo-700 leading-relaxed">
              One command indexes your repo, wires the hooks, and starts tracking savings, no session restart needed.
            </p>
          </div>
          <Link
            href="/tools/agent-booster"
            className="shrink-0 inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition-colors"
          >
            Get Agent Booster →
          </Link>
        </div>
      </section>

      <section id="guard-policy-reference">
        <SectionHeading id="guard-policy-reference">Policy reference</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Everything a security reviewer needs to evaluate ConductGuard: the rule schema, how decisions flow through the hook chain,
          and how policy changes propagate to every developer in real time.
        </p>

        <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 px-5 py-4 my-6">
          <p className="text-xs font-bold uppercase tracking-widest text-indigo-700 mb-2">Agentic Tool-Call Policy Schema v1 — the open category</p>
          <p className="text-sm text-stone-700 mb-3 leading-relaxed">
            A distinct policy shape: rules that govern what an AI agent may do when it invokes a tool. Two dialects — JSON at runtime, Cedar for portability. Bidirectional interchange with AWS Verified Permissions and any Cedar-native IAM stack. No lock-in.
          </p>
          <div className="flex flex-wrap gap-2">
            <a href="/docs/schema" className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-white border border-stone-200 text-xs text-stone-700 hover:border-indigo-400 hover:text-indigo-700 transition-colors">
              Schema overview →
            </a>
            <a href="https://github.com/sseshachala/conductai/blob/main/docs/guard/schema.md" className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-white border border-stone-200 text-xs text-stone-700 hover:border-indigo-400 hover:text-indigo-700 transition-colors">
              Full markdown reference →
            </a>
            <a href="https://github.com/sseshachala/conductai/blob/main/schemas/conduct-guard-rule.v1.json" className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-white border border-stone-200 text-xs text-stone-700 hover:border-indigo-400 hover:text-indigo-700 transition-colors font-mono">
              conduct-guard-rule.v1.json →
            </a>
          </div>
        </div>

        <SubHeading>Rule schema</SubHeading>
        <p className="text-stone-500 text-sm mb-3">Each rule in your policy JSON follows this shape:</p>
        <Pre>{`{
  // unique slug, used in audit log
  "id": "no-prod-push",

  "description": "Block git push to prod branches",

  // tool names: Bash, Write, Edit, MultiEdit, Read, Glob, mcp__*
  "applies_to": ["Bash"],

  // regex matched against tool input (command, file_path, etc.)
  "pattern": "git push.*main|master",

  // "block" | "warn" | "audit"
  "action": "block",

  // false = admin-only rule, cannot be disabled per-user
  "overridable": false,

  // "critical" | "high" | "medium" | "low"
  "severity": "high"
}`}</Pre>

        <div className="rounded-xl border border-stone-200 overflow-hidden my-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-36">Field</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-24">Type</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["id",          "string",  "Unique within policy. Appears in audit log events."],
                ["description", "string",  "Human-readable label shown in Guard dashboard."],
                ["applies_to",  "string[]","Tool names to match. Use [\"*\"] to catch all tools."],
                ["pattern",     "string",  "Python-compatible regex. Matched against the serialised tool input."],
                ["action",      "string",  "block = terminate call; warn = proceed + emit warning; audit = proceed silently + log."],
                ["overridable", "boolean", "false = rule cannot be suppressed by developers. Enforced by signed policy."],
                ["severity",    "string",  "Surfaces in dashboard and Slack alerts. Does not affect block/warn logic."],
              ].map(([f, t, n]) => (
                <tr key={f}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800">{f}</td>
                  <td className="px-4 py-3 font-mono text-xs text-stone-500">{t}</td>
                  <td className="px-4 py-3 text-xs text-stone-500">{n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>PreToolUse decision flow</SubHeading>
        <p className="text-stone-500 text-sm mb-4">
          Every time Claude Code is about to call a tool, the PreToolUse hook fires synchronously. This happens before the tool runs — giving Guard the ability to block it entirely.
        </p>
        <div className="rounded-xl border border-stone-200 bg-stone-50 px-5 py-4 mb-4 space-y-2 text-sm">
          {[
            ["1", "bg-stone-200 text-stone-700", "Tool call requested", "Claude invokes Bash / Write / Edit / mcp__* etc."],
            ["2", "bg-blue-100 text-blue-800",   "PreToolUse hook fires",  "posttooluse.py runs synchronously before the tool executes."],
            ["3", "bg-blue-100 text-blue-800",   "guard_check()",          "Serialised tool input matched against every active rule (regex, in order)."],
            ["4", "bg-red-100 text-red-800",     "BLOCK",                  "Hook exits non-zero → Claude Code aborts the tool call. Event written to audit log with decision=block."],
            ["4", "bg-amber-100 text-amber-800", "WARN",                   "Hook prints warning to stderr → tool proceeds. Event written with decision=warn."],
            ["4", "bg-emerald-100 text-emerald-800","ALLOW",               "No rule matched → tool proceeds. Event written with decision=allow (if audit mode on)."],
          ].map(([step, cls, label, desc], i) => (
            <div key={i} className="flex items-start gap-3">
              <span className={`shrink-0 mt-0.5 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${cls}`}>{step}</span>
              <div>
                <span className="font-semibold text-stone-800">{label} — </span>
                <span className="text-stone-500">{desc}</span>
              </div>
            </div>
          ))}
        </div>

        <SubHeading>PostToolUse lifecycle</SubHeading>
        <p className="text-stone-500 text-sm mb-4">
          After a tool completes, the PostToolUse hook fires to record what actually happened — token usage, blast radius, and any post-run policy checks.
        </p>
        <Pre>{`PostToolUse fires
  └─ read token counts from tool response
  └─ _compute_blast_radius(tool_name, tool_input, tool_response)
       → { files: N, symbols?: N, tier: "local"|"repo"|"network"|"destructive" }
  └─ _post_usage(tokens_in, tokens_out, blast_radius=…)
       → POST /guard/events/usage   ← updates audit event row in-place
  └─ journal_append(event)          ← async: drain daemon POSTs to API every 30s`}</Pre>

        <p className="text-stone-500 text-sm mt-3 mb-4">
          The <strong>blast radius</strong> column in the Guard Activity log is populated here. <Code>destructive</Code> tier commands (rm -rf, force-push, DROP TABLE) are flagged immediately; <Code>network</Code> tier captures outbound calls; <Code>repo</Code> tier tracks cross-repo mutations; <Code>local</Code> covers single-file writes.
        </p>

        <SubHeading>Policy propagation</SubHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          A Guard policy is a signed JSON file. When an admin publishes a new policy from the dashboard, the signature is written server-side and the policy version incremented. The drain daemon running on each developer machine polls <Code>/guard/policy/latest</Code> every 30 seconds. On version change it writes the new policy to <Code>~/.conductguard/policy.json</Code> and verifies the Ed25519 signature before activating it.
        </p>
        <div className="rounded-xl border border-stone-200 bg-stone-50 px-5 py-4 mb-4 space-y-2 text-sm">
          {[
            ["Admin publishes policy",    "Dashboard signs + stores policy. Version counter incremented."],
            ["Drain daemon polls (30s)",  "GET /guard/policy/latest — returns version + signed payload."],
            ["Signature verified",        "Ed25519 public key from ~/.conductguard/public.pem checked. Tampered policy rejected."],
            ["Policy written atomically", "policy.json swapped atomically. Next PreToolUse call loads new rules."],
          ].map(([step, desc]) => (
            <div key={step} className="flex items-start gap-3">
              <span className="shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full bg-indigo-400 mt-2" />
              <div>
                <span className="font-semibold text-stone-800">{step} — </span>
                <span className="text-stone-500">{desc}</span>
              </div>
            </div>
          ))}
        </div>
        <p className="text-stone-500 text-sm leading-relaxed">
          No redeploy, no agent restart, no per-developer action required. A rule change published at 14:00 is active on every enrolled developer machine by 14:01. <Code>overridable: false</Code> rules are enforced by the signed policy — a developer cannot remove them by editing a local config file.
        </p>

        <div className="mt-8 rounded-xl border border-stone-200 bg-stone-50 px-5 py-4">
          <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-3">Supported tool names in <code>applies_to</code></p>
          <div className="flex flex-wrap gap-2">
            {["Bash","Write","Edit","MultiEdit","Read","Glob","Grep","mcp__*","WebFetch","WebSearch","*"].map(t => (
              <span key={t} className="px-2.5 py-1 rounded-lg bg-white border border-stone-200 font-mono text-xs text-stone-700">{t}</span>
            ))}
          </div>
          <p className="text-xs text-stone-400 mt-3">Use <Code>*</Code> to match every tool. MCP tools are matched by prefix — <Code>mcp__agent-booster__*</Code> matches all Agent Booster tools.</p>
        </div>
      </section>
    </>
  )
}
