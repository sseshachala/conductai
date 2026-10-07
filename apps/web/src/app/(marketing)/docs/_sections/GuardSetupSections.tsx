import { marked } from "marked"
// @ts-expect-error - .md imported as raw string via webpack asset/source
import oktaTrackingMd from "../../../../../../../docs/reference/okta-tracking.md"
import { Code, Pre, SectionHeading, SubHeading } from "./shared"

export function GuardSetupSections() {
  return (
    <>
      <section id="guard">
        <SectionHeading id="guard">ConductGuard. Overview</SectionHeading>
        <div className="rounded-lg border-l-4 border-indigo-500 bg-indigo-50 px-4 py-3 mb-6">
          <p className="text-sm font-semibold text-indigo-900 leading-snug">
            GitHub gives the CISO a setting. ConductGuard gives them enforcement.
          </p>
          <p className="text-xs text-indigo-700 mt-1 leading-relaxed">
            Most AI tool governance is a toggle the user can flip off. Guard is a proxy — one env var routes every LLM call through it regardless of framework, language, or developer discipline. Actions Guard denies are not unlikely. They are structurally impossible.
          </p>
        </div>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          ConductGuard is the team policy layer for AI tools. It has two enforcement surfaces:
        </p>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-8">
          {[
            { label: "Workflow enforcement (Agent guard)", detail: "Automatic policy check before every agentic AI step. No YAML block needed, the executor hook evaluates active policies against the run state and halts, warns, or audits based on the workspace enforcement mode." },
            { label: "Local enforcement (hook + MCP)",     detail: "Intercepts AI tool calls in Claude Code, Cursor, and other editors before they reach the model. Checks hard caps, evaluates policies, and blocks or warns at call time. No workflow required." },
          ].map(({ label, detail }) => (
            <div key={label} className="px-4 py-3">
              <p className="font-medium text-stone-800 mb-0.5">{label}</p>
              <p className="text-stone-500 text-xs leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>

        <SubHeading>Policy anatomy</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-40">Field</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-sm">
              {[
                ["match_tool",         "Which AI tool triggers this rule (e.g. claude-code, cursor, * for any)."],
                ["match_pattern",      "Regex matched against the serialized tool call input. Trigger if matched."],
                ["match_path_pattern", "Regex matched against file paths in the tool call. Trigger if matched."],
                ["enforcement_mode",   "block | warn | audit, what happens when the rule triggers."],
                ["alert_message",      "Message sent to Slack when the rule triggers (if Slack is configured)."],
              ].map(([field, desc]) => (
                <tr key={field}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800 align-top">{field}</td>
                  <td className="px-4 py-3 text-xs text-stone-500 leading-relaxed">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="guard-agent">
        <SectionHeading id="guard-agent">Agent guard</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          Agent guard is an automatic policy check that runs before every <Code>mode: agentic</Code> brain block in a
          workflow. No YAML block needed, it fires as an executor hook and records results in the run trace.
        </p>

        <SubHeading>Enforcement modes</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-28">Mode</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Behaviour</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-sm">
              {[
                ["block", "Run halts immediately, the AI step never executes. Use for hard policy lines (e.g. no access to prod repos)."],
                ["warn",  "Policy match is flagged in the run trace and the Steps tab, but the run continues. Default for new workspaces."],
                ["audit", "Match is recorded silently in Guard activity. No interruption visible to the developer or the run."],
              ].map(([mode, desc]) => (
                <tr key={mode}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800 align-top">{mode}</td>
                  <td className="px-4 py-3 text-xs text-stone-500 leading-relaxed">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>Disabling per run</SubHeading>
        <p className="text-stone-500 text-sm mb-3">
          The run trigger modal has a <strong>Guard</strong> toggle (on by default). Flip it off before firing a run to
          skip the auto-hook for that run only, useful for local dev and debugging. The toggle sends{" "}
          <Code>guard_enabled: false</Code> in the run payload.
        </p>

        <SubHeading>Where to configure</SubHeading>
        <p className="text-stone-500 text-sm mb-2">
          Workspace-level enforcement mode lives in <strong>Guard → Settings → Agent guard</strong>. The selected mode
          applies to all runs in the workspace unless overridden per-run.
        </p>
        <p className="text-stone-500 text-sm">
          Guard must be installed (Guard config present) for the hook to evaluate policies. If Guard is not installed the
          hook skips silently, no runs are blocked.
        </p>
      </section>

      <section id="guard-user-flow">
        <SectionHeading id="guard-user-flow">Developer setup</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          Guard is provisioned automatically at login, no separate install step. One command wires up the hook,
          registers the MCP server, and downloads active policies.
        </p>

        <Pre>{`# 1. Install the CLI (once)
pip install conduct-cli

# 2. Generate an API key. Settings → API Keys (admin or developer role)
# 3. Login. Guard sets itself up automatically
conduct login --server https://api.conductai.ai --api-key cond_live_xxxx

# That's it. Guard is now active. Verify:
conduct guard status`}</Pre>

        <p className="text-stone-500 text-sm mt-4 mb-3">
          Login auto-provisions Guard by calling <Code>GET /guard/config/installed</Code>, downloading the workspace
          policy file to <Code>~/.conductguard/policy.json</Code>, writing the hook script to{" "}
          <Code>~/.conductguard/hook.py</Code>, and registering it in every AI tool config found on the machine.
        </p>

        <SubHeading>Guard CLI commands</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-56">Command</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["conduct guard status", "Show policy count, today's spend, violations, and active developer info"],
                ["conduct guard sync",   "Pull latest policies from the server and refresh the hook script in all tools"],
                ["conduct guard audit",  "Show recent activity log (last 24 h by default, --since 7d for a week)"],
                ["conduct guard approvals list",           "List Guard HITL approval requests (--status pending|approved|rejected|all)"],
                ["conduct guard approvals approve <id>",     "Approve a pending HITL request from the terminal (--reason optional)"],
                ["conduct guard approvals reject <id>",      "Reject a pending HITL request from the terminal"],
              ].map(([cmd, desc]) => (
                <tr key={cmd}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800">{cmd}</td>
                  <td className="px-4 py-3 text-xs text-stone-500">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>Auto-update</SubHeading>
        <p className="text-stone-500 text-sm mb-3">
          The CLI checks PyPI for a newer version on every command (cached 24 h). If one is found it upgrades
          itself and re-runs the original command, developers never need to manually update.
          Set <Code>CONDUCT_NO_AUTOUPDATE=1</Code> to disable (useful in CI).
        </p>
      </section>

      <section id="guard-sync">
        <SectionHeading id="guard-sync">Sync &amp; re-sync</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          Each developer machine caches a local copy of the workspace policy file at{" "}
          <Code>~/.conductguard/policy.json</Code>. The Guard hook checks the server version on every tool call,
          throttled to one network request per 60 seconds. If the version has changed, the hook silently
          re-downloads the policy before evaluating the current call, no manual action needed.
        </p>

        <SubHeading>When a re-sync is triggered</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            ["Policy created / edited / deleted", "Server version timestamp updates. Each machine re-syncs on the next tool call after its 60s window expires."],
            ["Re-sync button (Guard → Settings)",  "Bumps resync_requested_at on the workspace. Machines pick it up on the next tool call after the 60s cache window."],
            ["conduct guard sync (CLI)",           "Forces an immediate pull regardless of cached version. Useful after a network gap, machine restore, or when you need instant propagation."],
          ].map(([trigger, detail]) => (
            <div key={trigger} className="px-4 py-3">
              <p className="font-medium text-stone-800 text-xs mb-0.5">{trigger}</p>
              <p className="text-stone-500 text-xs leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>

        <SubHeading>Sync status card</SubHeading>
        <p className="text-stone-500 text-sm mb-2">
          <strong>Guard → Settings</strong> shows a live <em>Sync status</em> card: <Code>synced / total</Code> machines
          in green when all developers are up to date, amber when any machine hasn{"'"}t pulled the latest version yet.
          The count comes from the <Code>/guard/developer-tools</Code> endpoint which tracks per-developer tool
          coverage snapshots pushed at login and by <Code>conduct guard sync</Code>.
        </p>
      </section>

      <section id="guard-hook">
        <SectionHeading id="guard-hook">Hook & tool coverage</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          Guard uses two enforcement surfaces depending on the AI tool. Both are registered automatically at login.
        </p>

        <SubHeading>Coverage by tool</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Tool</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Mechanism</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Enforcement</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["Claude Code", "PreToolUse · PreCompact · SessionStart hooks (~/.claude/settings.json)", "Hard block, every tool call intercepted; session state preserved across compaction"],
                ["Codex CLI",   "PreToolUse hook (~/.codex/hooks.json)",     "Hard block, same script, same exit-code-2 protocol"],
                ["Cursor",      "MCP server (conductguard-mcp)",             "Advisory. AI sees Guard tools, can self-enforce"],
                ["Windsurf",    "MCP server (conductguard-mcp)",             "Advisory. AI sees Guard tools, can self-enforce"],
              ].map(([tool, mech, enf]) => (
                <tr key={tool}>
                  <td className="px-4 py-3 text-xs font-medium text-stone-800">{tool}</td>
                  <td className="px-4 py-3 font-mono text-xs text-stone-500">{mech}</td>
                  <td className="px-4 py-3 text-xs text-stone-500">{enf}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>What the hook does on every call</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            ["1. Budget check (cached 5 min)", "Calls GET /guard/spend/budget-check. If the hard cap is hit, exits with code 2, the tool treats this as a block."],
            ["2. Policy evaluation",           "Loads ~/.conductguard/policy.json. Evaluates match_tool, match_pattern, and match_path_pattern. block exits 2, warn prints a message, audit falls through."],
            ["3. Event posted (async)",        "Every tool call, allowed or blocked, is posted to /guard/events. This powers the Activity log and Active developers metrics."],
            ["4. Slack alert",                 "If a block or warn rule has an alert configured, the Guard API notifies the workspace's Slack channel."],
          ].map(([step, desc]) => (
            <div key={step} className="flex gap-4 px-4 py-3">
              <span className="font-medium text-stone-700 w-52 shrink-0 text-xs">{step}</span>
              <span className="text-stone-500 text-xs leading-relaxed">{desc}</span>
            </div>
          ))}
        </div>

        <SubHeading>Session persistence across compaction</SubHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          When Claude Code compacts a long conversation, guard state (budget position, recent blocks, active workspace) would otherwise be lost. ConductGuard wires two additional hooks to preserve context across compaction events.
        </p>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            ["PreCompact hook", "Fires before compaction. Writes a priority-tiered snapshot to .booster/session_snapshot.json. Tier 1: git branch + last 3 commits, memory index headline; Tier 2: guard budget state (via conductguard status --json); Tier 3: cwd metadata. Write is atomic (tmp → rename) and never blocks Claude Code on failure."],
            ["SessionStart hook", "Fires when a new session opens. Reads the snapshot if it exists and is under 2 hours old, then injects a ≤5-line context reminder into Claude's view: branch, last commit, guard budget %, and memory index headline. Skips silently if snapshot is stale or missing."],
            ["Snapshot location", ".booster/session_snapshot.json in the project root. Three priority tiers ensure critical state is always preserved, lower-priority metadata is dropped if space is tight."],
          ].map(([step, desc]) => (
            <div key={step} className="flex gap-4 px-4 py-3">
              <span className="font-medium text-stone-700 w-44 shrink-0 text-xs">{step}</span>
              <span className="text-stone-500 text-xs leading-relaxed">{desc}</span>
            </div>
          ))}
        </div>

        <SubHeading>Covered tools, confirmed in the wild</SubHeading>
        <p className="text-stone-500 text-sm mb-5 leading-relaxed">
          ConductGuard has been tested and confirmed working on the following tools. Hard block means every tool call. Bash, Read, Edit, Write, is intercepted before execution and stopped cold at the PreToolUse hook.
        </p>
        <div className="grid grid-cols-1 gap-4 mb-6 sm:grid-cols-2">

          <div className="rounded-xl border border-stone-200 overflow-hidden">
            <div className="px-4 py-3 flex items-center justify-between border-b border-stone-100 bg-stone-50">
              <span className="font-semibold text-stone-800 text-sm">Claude Code</span>
              <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">✓ Live</span>
            </div>
            <div className="px-4 py-3 text-xs text-stone-500 space-y-1 border-b border-stone-100">
              <div><span className="font-medium text-stone-700">Hook:</span> PreToolUse · PostToolUse · Stop</div>
              <div><span className="font-medium text-stone-700">Enforcement:</span> Hard block, exit code 2</div>
              <div><span className="font-medium text-stone-700">Config:</span> <code className="font-mono bg-stone-100 px-1 rounded">~/.claude/settings.json</code></div>
            </div>
            <div className="p-3 bg-stone-950 space-y-1 font-mono text-xs">
              <p className="text-stone-500"># Claude Code, budget hard cap hit</p>
              <p className="text-amber-400">• PreToolUse hook (blocked)</p>
              <p className="text-stone-300 pl-2">feedback: [ConductGuard] Your team&apos;s monthly</p>
              <p className="text-stone-300 pl-2">AI budget of $650.00 has been reached.</p>
              <p className="text-stone-300 pl-2">New tool calls are paused until the limit</p>
              <p className="text-stone-300 pl-2">is raised. Contact your security team.</p>
              <p className="text-stone-500 mt-2"># Every tool call blocked until cap raised</p>
              <p className="text-amber-400">• PreToolUse hook (blocked)</p>
              <p className="text-amber-400">• PreToolUse hook (blocked)</p>
              <p className="text-amber-400">• PreToolUse hook (blocked)</p>
            </div>
          </div>

          <div className="rounded-xl border border-stone-200 overflow-hidden">
            <div className="px-4 py-3 flex items-center justify-between border-b border-stone-100 bg-stone-50">
              <span className="font-semibold text-stone-800 text-sm">Codex CLI</span>
              <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">✓ Live</span>
            </div>
            <div className="px-4 py-3 text-xs text-stone-500 space-y-1 border-b border-stone-100">
              <div><span className="font-medium text-stone-700">Hook:</span> PreToolUse</div>
              <div><span className="font-medium text-stone-700">Enforcement:</span> Hard block, exit code 2</div>
              <div><span className="font-medium text-stone-700">Config:</span> <code className="font-mono bg-stone-100 px-1 rounded">~/.codex/hooks.json</code></div>
            </div>
            <div className="p-3 bg-stone-950 space-y-1 font-mono text-xs">
              <p className="text-stone-500"># Codex CLI, same hook, same block</p>
              <p className="text-amber-400">• PreToolUse hook (blocked)</p>
              <p className="text-stone-300 pl-2">feedback: [ConductGuard] Your team&apos;s monthly</p>
              <p className="text-stone-300 pl-2">AI budget of $650.00 has been reached.</p>
              <p className="text-stone-300 pl-2">New tool calls are paused until the limit</p>
              <p className="text-stone-300 pl-2">is raised. Contact your security team.</p>
              <p className="text-stone-400 mt-2 italic"># Codex stopped cold, same script,</p>
              <p className="text-stone-400 italic"># same exit-code-2 protocol as Claude Code</p>
            </div>
          </div>

          <div className="rounded-xl border border-stone-200 overflow-hidden opacity-60">
            <div className="px-4 py-3 flex items-center justify-between border-b border-stone-100 bg-stone-50">
              <span className="font-semibold text-stone-800 text-sm">Cursor</span>
              <span className="text-xs font-semibold text-stone-500 bg-stone-100 border border-stone-200 px-2 py-0.5 rounded-full">Coming soon</span>
            </div>
            <div className="px-4 py-3 text-xs text-stone-400 space-y-1">
              <div><span className="font-medium text-stone-500">Hook:</span> MCP server (advisory)</div>
              <div><span className="font-medium text-stone-500">Enforcement:</span> Advisory. AI self-enforces via Guard MCP tools</div>
              <div><span className="font-medium text-stone-500">Hard block:</span> In development</div>
            </div>
          </div>

          <div className="rounded-xl border border-stone-200 overflow-hidden opacity-60">
            <div className="px-4 py-3 flex items-center justify-between border-b border-stone-100 bg-stone-50">
              <span className="font-semibold text-stone-800 text-sm">Windsurf</span>
              <span className="text-xs font-semibold text-stone-500 bg-stone-100 border border-stone-200 px-2 py-0.5 rounded-full">Coming soon</span>
            </div>
            <div className="px-4 py-3 text-xs text-stone-400 space-y-1">
              <div><span className="font-medium text-stone-500">Hook:</span> MCP server (advisory)</div>
              <div><span className="font-medium text-stone-500">Enforcement:</span> Advisory. AI self-enforces via Guard MCP tools</div>
              <div><span className="font-medium text-stone-500">Hard block:</span> In development</div>
            </div>
          </div>

        </div>

        <div className="rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-700">
          <strong>Exit codes:</strong> 0 = pass (tool runs), 2 = block (tool aborted).
          The tool surfaces the rule message to the developer so they know why the call was blocked.
        </div>
      </section>

      <section id="guard-mcp">
        <SectionHeading id="guard-mcp">conductguard-mcp</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          An MCP server that gives Cursor, Windsurf, and any MCP-compatible editor direct access to Guard.
          Registered automatically at login. The AI can query its own policies before taking sensitive actions.
        </p>

        <SubHeading>Auto-registered config (written by conduct login)</SubHeading>
        <Pre>{`# Written to ~/.cursor/mcp.json, ~/.windsurf/mcp.json, ~/.codex/mcp.json
# and ~/.claude/settings.json, whichever exist on the machine.
{
  "mcpServers": {
    "conductguard": {
      "command": "conductguard-mcp",
      "args": ["--workspace", "<workspace-id>", "--token", "<member-token>", "--api-url", "https://api.conductai.ai"]
    }
  }
}`}</Pre>

        <SubHeading>Tools exposed</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            { tool: "guard_status", desc: "Returns workspace ID, policy count, policy version, and developer email. Useful for confirming Guard is active.", args: "None" },
            { tool: "guard_check",  desc: "Evaluates a tool call against active policies. Returns ALLOWED, BLOCKED, or WARNING with the matching rule.", args: "tool_name (str), tool_input (object), pack (str, optional), prompt (str, optional)" },
            { tool: "guard_sync",   desc: "Pulls the latest policies from the server and writes them to ~/.conductguard/policy.json.", args: "None" },
          ].map(({ tool, desc, args }) => (
            <div key={tool} className="px-4 py-3">
              <div className="flex items-center gap-2 mb-1">
                <code className="font-mono text-xs font-semibold text-stone-800 bg-stone-100 px-1.5 py-0.5 rounded">{tool}</code>
                <span className="text-[10px] text-stone-400">args: {args}</span>
              </div>
              <p className="text-xs text-stone-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
        <p className="text-stone-500 text-sm">JSON-RPC 2.0 over stdio. Protocol version <Code>2024-11-05</Code>.</p>

        <SubHeading>guard_check parameters</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-4">
          {[
            ["tool_name", "required", "Name of the tool being called (e.g. bash, Write, WebFetch)."],
            ["tool_input", "required", "Input arguments as an object. Serialised and matched against active rules."],
            ["pack",       "optional", "Scope evaluation to a specific compliance pack (e.g. conduct-owasp, conduct-soc2). Omit to use workspace default policy."],
            ["prompt",     "optional", "User prompt context. Prepended to the audit log entry — helps trace which instruction triggered the action."],
          ].map(([param, req, desc]) => (
            <div key={param} className="flex gap-4 px-4 py-3 items-start">
              <code className="font-mono text-xs font-semibold text-stone-800 bg-stone-100 px-1.5 py-0.5 rounded w-24 shrink-0">{param}</code>
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0 mt-0.5 ${req === "required" ? "bg-rose-50 text-rose-600" : "bg-stone-100 text-stone-500"}`}>{req}</span>
              <span className="text-xs text-stone-500 leading-relaxed">{desc}</span>
            </div>
          ))}
        </div>
      </section>

      <section id="guard-tokens">
        <SectionHeading id="guard-tokens">Agent tokens</SectionHeading>
        <p className="text-stone-500 text-sm mb-5 leading-relaxed">
          Guard issues two token types. Both work with the proxy and MCP endpoint and write to the same audit trail.
        </p>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-5">
          {[
            ["cond_agt_*", "Session token",  "8 hours",    "conduct login",        "Interactive tools — Claude Code, Cursor, Windsurf, Codex CLI."],
            ["cond_api_*", "API token",      "Long-lived", "Agent Identity page",  "CI/CD, server agents, integrations. Revocable from the dashboard."],
          ].map(([prefix, label, ttl, source, use]) => (
            <div key={prefix} className="px-4 py-4">
              <div className="flex items-center gap-2 mb-2">
                <code className="font-mono text-xs font-semibold text-stone-800 bg-stone-100 px-1.5 py-0.5 rounded">{prefix}</code>
                <span className="text-[10px] font-semibold text-stone-500 bg-stone-50 border border-stone-200 px-1.5 py-0.5 rounded">{label}</span>
                <span className="text-[10px] text-stone-400">expires: {ttl}</span>
              </div>
              <p className="text-xs text-stone-500 leading-relaxed"><span className="text-stone-700 font-medium">Issued by:</span> {source} &nbsp;·&nbsp; <span className="text-stone-700 font-medium">Use for:</span> {use}</p>
            </div>
          ))}
        </div>

        <SubHeading>RFC 8693 token exchange</SubHeading>
        <Pre>{`POST /oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=<clerk_jwt>
&subject_token_type=urn:ietf:params:oauth:token-type:jwt
&resource=<workspace_id>

# Response
{
  "access_token": "cond_agt_...",
  "token_type": "Bearer",
  "expires_in": 28800,
  "refresh_token": "cond_ref_...",
  "workspace_id": "<uuid>"
}`}</Pre>
        <p className="text-stone-500 text-xs mt-3">
          conduct login calls this endpoint automatically after browser auth. Older CLI installs may still POST to <Code>/token</Code>; that URL is a backwards-compat alias for the same handler and will be removed after ~60 days of zero traffic.
        </p>

        <SubHeading>OAuth 2.1 (native MCP client discovery)</SubHeading>
        <p className="text-stone-500 text-sm mb-3 leading-relaxed">
          Spec-compliant MCP clients (Claude.ai native "Add MCP", Cursor, etc.) discover and authenticate against Conduct without a pasted token. The chain:
        </p>
        <ol className="text-stone-500 text-sm leading-relaxed mb-4 list-decimal ml-5 space-y-1">
          <li>Client hits <Code>https://gateway.conductai.ai/mcp</Code>, receives 401 with <Code>WWW-Authenticate: Bearer resource_metadata=…</Code>.</li>
          <li>Client fetches <Code>/.well-known/oauth-protected-resource/mcp</Code>, follows <Code>authorization_servers</Code>.</li>
          <li>Client fetches <Code>/.well-known/oauth-authorization-server</Code>, reads endpoints.</li>
          <li>Client self-registers via <Code>POST /oauth/register</Code> (RFC 7591 DCR).</li>
          <li>Client redirects user to <Code>/oauth/authorize</Code> with PKCE S256 challenge; user signs in with Clerk.</li>
          <li>Client redeems the returned code at <Code>POST /oauth/token</Code> and uses the <Code>cond_agt_*</Code> access token for MCP calls.</li>
        </ol>
        <p className="text-stone-500 text-xs mt-1">
          PKCE S256 is mandatory (OAuth 2.1). Confidential clients (with <Code>client_secret</Code>) are not supported — public clients only. Refresh tokens rotate on every use.
        </p>
      </section>

      <section id="guard-okta-tracking" className="[&_h2]:text-lg [&_h2]:font-semibold [&_h2]:mt-6 [&_h2]:mb-3 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:mt-5 [&_h3]:mb-2 [&_p]:text-sm [&_p]:text-stone-500 [&_p]:leading-relaxed [&_p]:mb-3 [&_ul]:text-sm [&_ul]:text-stone-500 [&_ul]:list-disc [&_ul]:ml-5 [&_ul]:mb-3 [&_li]:mb-1 [&_code]:font-mono [&_code]:text-xs [&_code]:bg-stone-100 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_table]:text-xs [&_table]:mb-4 [&_table]:border [&_table]:border-stone-200 [&_table]:w-full [&_th]:bg-stone-50 [&_th]:text-left [&_th]:font-semibold [&_th]:p-2 [&_th]:border-b [&_th]:border-stone-200 [&_td]:p-2 [&_td]:border-b [&_td]:border-stone-100 [&_td]:align-top [&_a]:text-indigo-600 [&_a:hover]:underline [&_strong]:font-semibold [&_strong]:text-stone-700"
        dangerouslySetInnerHTML={{ __html: marked.parse(oktaTrackingMd, { async: false }) as string }}
      />

      <section id="guard-spend">
        <SectionHeading id="guard-spend">Spend controls</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Guard tracks AI spend per developer. Admins set budgets in Guard → Spend.
          When a developer hits their hard cap, the hook blocks their next tool call.
        </p>

        <SubHeading>Budget hierarchy</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            ["Workspace hard limit", "Monthly cap for the entire workspace. When the total hits this limit, all developers are blocked."],
            ["Per-developer limit",  "Monthly cap per developer. Set in Guard → Spend → Budgets."],
            ["Alert threshold",      "Optional, percentage of budget at which Slack alerts fire (e.g. 80%). Developers continue past the threshold; the hard limit is the actual block."],
          ].map(([label, desc]) => (
            <div key={label} className="flex gap-4 px-4 py-3">
              <span className="font-medium text-stone-700 w-44 shrink-0 text-xs">{label}</span>
              <span className="text-stone-500 text-xs leading-relaxed">{desc}</span>
            </div>
          ))}
        </div>

        <SubHeading>Budget check API</SubHeading>
        <Pre>{`GET /guard/spend/budget-check?workspace_id=<uuid>

# Response
{ "hard_blocked": false, "monthly_cost_usd": 12.40, "hard_limit_usd": 50.00 }

# When blocked:
{ "hard_blocked": true, "reason": "Monthly budget of $50.00 exceeded ($51.20 used)", ... }`}</Pre>

        <div className="mt-3 rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-700">
          The hook caches the response at <Code>~/.conductguard/budget_cache.json</Code> for 5 minutes.
          Delete it to force an immediate re-check.
        </div>
      </section>
    </>
  )
}
