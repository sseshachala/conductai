import { Code, Pre, Screenshot, SectionHeading, SubHeading } from "./shared"

export function GuardSavingsSections() {
  return (
    <>
      <section id="guard-savings">
        <SectionHeading id="guard-savings">Maximize savings</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Guard tracks AI spend, but the real leverage is reducing how many tokens your team burns in the first place.
          Two tools stack on top of each other to compress token usage before it hits the model.
          Guard captures the combined savings and shows them on the Spend dashboard.
        </p>

        {/* Real numbers comparison */}
        <div className="rounded-xl border-2 border-stone-200 overflow-hidden mb-3">
          <div className="grid grid-cols-3 divide-x divide-stone-200">
            {[
              {
                state: "No optimisation",
                bg: "bg-white",
                tokens: "34.8M",
                tokenLabel: "tokens consumed (command output)",
                saved: "$0",
                savedLabel: "saved",
                savedColor: "text-stone-300",
                rate: "—",
                rateLabel: "savings rate",
                detail: "Full git diff, full test log, full build output fed into context on every tool call.",
              },
              {
                state: "+ RTK",
                bg: "bg-indigo-50",
                tokens: "286K",
                tokenLabel: "tokens consumed (after filtering)",
                saved: "$103.51",
                savedLabel: "saved (real, this install)",
                savedColor: "text-indigo-600",
                rate: "99.2%",
                rateLabel: "across 3,316 commands",
                detail: "Failures only. Compact diffs. Deduped logs. 34.5M tokens that never entered the context window.",
              },
              {
                state: "+ RTK + Agent Booster",
                bg: "bg-green-50",
                tokens: "57.8K",
                tokenLabel: "tokens served from file reads",
                saved: "$103.80",
                savedLabel: "saved combined (real)",
                savedColor: "text-green-600",
                rate: "62%",
                rateLabel: "on file reads (30 reads)",
                detail: "Symbol-slice reads on top of RTK. Only the relevant function or class enters context, not the whole file.",
              },
            ].map(({ state, bg, tokens, tokenLabel, saved, savedLabel, savedColor, rate, rateLabel, detail }) => (
              <div key={state} className={`${bg} px-4 py-4`}>
                <p className="text-[10px] font-bold text-stone-500 uppercase tracking-wider mb-3">{state}</p>
                <p className="text-2xl font-bold text-stone-900 leading-none">{tokens}</p>
                <p className="text-[10px] text-stone-400 mb-3">{tokenLabel}</p>
                <p className={`text-lg font-bold ${savedColor}`}>{saved}</p>
                <p className="text-[10px] text-stone-400 mb-3">{savedLabel}</p>
                <p className="text-sm font-semibold text-stone-700">{rate}</p>
                <p className="text-[10px] text-stone-400 mb-3">{rateLabel}</p>
                <p className="text-xs text-stone-500 leading-relaxed border-t border-stone-200 pt-3 mt-1">{detail}</p>
              </div>
            ))}
          </div>
        </div>
        <p className="text-xs text-stone-400 mb-8">
          Real numbers from a single developer install. RTK: 3,316 commands, 34.5M tokens saved at Claude Sonnet input pricing ($3/M tokens).
          Agent Booster: 30 reads, 96K tokens saved. Combined: 34.6M tokens, $103.80 saved.
        </p>

        {/* RTK install block */}
        <SubHeading>RTK, token optimizer for command output</SubHeading>
        <p className="text-stone-500 text-sm mb-3 leading-relaxed">
          RTK (Rust Token Killer) wraps every shell command Claude Code runs, git, test, build, docker, and strips noise before it
          enters the context window. Failures only. Compact diffs. Deduplicated logs. 60–99% savings depending on command type.
        </p>
        <Pre>{`# Install
pip install rtk-cli   # or: cargo install rtk

# See your savings at any time
rtk gain

# Real output (single developer install):
# Total commands:  3,316
# Tokens saved:    34.5M  (99.2%)
# Est. cost saved: $103.51  (at Claude Sonnet $3/M input)`}</Pre>
        <div className="mt-3 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-800 mb-8">
          <strong>Guard integration (coming soon):</strong> Once RTK is installed, Guard reads <Code>rtk gain</Code> at each sync,
          diffs against the last baseline, and posts the delta to the Spend dashboard automatically.
          Your team's real savings appear in the <strong>Est. savings</strong> card, not zero.
        </div>

        {/* Agent Booster install block */}
        <SubHeading>Agent Booster, token optimizer for file reads</SubHeading>
        <p className="text-stone-500 text-sm mb-3 leading-relaxed">
          Agent Booster indexes your codebase and serves only the relevant symbol slice when Claude reads a file, the
          function, class, or block it actually needs, not the entire 800-line file. 62% savings on file reads observed in practice.
          Also cuts <strong>output</strong> tokens via verbosity modes and compresses project memory. Stacks on top of RTK.
        </p>
        <Pre>{`# Install
pip install agent-booster

# Index your repo + wire hooks
booster init claude

# Set verbosity mode, cuts output tokens 30–75%
booster verbosity full     # lite | full | ultra | off

# Compress memory files via haiku (~60% smaller)
booster compress           # add --dry-run to preview

# See combined input + output savings
booster gain

# Real output (6 active days):
# Tokens saved (reads):   1,208,085  (77%)
# Tokens saved (output):  ~1,833     (full verbosity)
# Combined savings:       ~1,209,918 tokens`}</Pre>
        <div className="mt-3 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800 mb-4">
          <strong>Guard integration:</strong> The <Code>booster-stop.py</Code> Stop hook captures actual output tokens at each session end and stores them locally. <Code>conduct guard sync</Code> ships them to Guard alongside RTK savings.
          The combined RTK + Booster delta appears as <strong>Est. savings</strong> on the Guard Spend dashboard, broken down by developer.
        </div>

        {/* Savings breakdown table */}
        <SubHeading>What Guard will show</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Source</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">What it compresses</th>
                <th className="text-right px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Typical rate</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Tracked by</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["RTK",               "Command output, git, test, build, docker, grep", "85–99%", "rtk gain -f json"],
                ["Booster, reads",   "File reads, serves symbol slices, not full files",  "50–70%", "booster gain"],
                ["Booster, output",  "Response verbosity (lite/full/ultra modes)",          "30–75%", "booster gain"],
                ["Combined",          "All layers stacked in the same session",              "90–94%", "Guard sync posts delta"],
              ].map(([src, what, rate, how]) => (
                <tr key={src}>
                  <td className="px-4 py-3 text-xs font-semibold text-stone-800">{src}</td>
                  <td className="px-4 py-3 text-xs text-stone-500">{what}</td>
                  <td className="px-4 py-3 text-xs text-right font-mono text-green-600">{rate}</td>
                  <td className="px-4 py-3 text-xs font-mono text-stone-400">{how}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="guard-roles">
        <SectionHeading id="guard-roles">Roles & permissions</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Every workspace member has one of four roles, the single source of truth enforced across Guard, API keys, and the CLI.
        </p>

        <SubHeading>Role definitions</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-8">
          {[
            { role: "Admin",     color: "bg-purple-50 text-purple-700", desc: "Full access: Guard policies, spend limits, members, settings, API key revoke, and all playbooks." },
            { role: "Security",  color: "bg-blue-50 text-blue-700",     desc: "Full Guard access, create/edit policies and view all activity. View-only spend. Cannot manage members or revoke API keys." },
            { role: "Developer", color: "bg-green-50 text-green-700",   desc: "View-only Guard (no create/edit). Can generate their own API key. Full access to runs, playbooks, and canvas." },
            { role: "Viewer",    color: "bg-stone-100 text-stone-600",  desc: "View-only across all of Guard, runs, and audit log. No execution or edit rights." },
          ].map(({ role, color, desc }) => (
            <div key={role} className="flex items-start gap-4 px-4 py-3">
              <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full shrink-0 mt-0.5 ${color}`}>{role}</span>
              <span className="text-xs text-stone-500 leading-relaxed">{desc}</span>
            </div>
          ))}
        </div>

        <SubHeading>Guard capability matrix</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Capability</th>
                {["Admin", "Security", "Developer", "Viewer"].map(h => (
                  <th key={h} className="text-center px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-20">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-sm">
              {[
                ["View Guard dashboard",     true,  true,  true,  true ],
                ["View activity log",        true,  true,  true,  true ],
                ["View policies",            true,  true,  true,  true ],
                ["Create / edit policies",   true,  true,  false, false],
                ["View spend data",          true,  true,  true,  true ],
                ["Set spend limits",         true,  false, false, false],
                ["View members",             true,  true,  true,  true ],
                ["Invite / remove members",  true,  false, false, false],
                ["Configure Guard settings", true,  false, false, false],
                ["Generate API key",         true,  false, true,  false],
                ["Revoke API key",           true,  false, false, false],
                ["Run playbooks / canvas",   true,  true,  true,  false],
              ].map(([label, admin, security, developer, viewer]) => (
                <tr key={label as string}>
                  <td className="px-4 py-2.5 text-xs text-stone-700">{label as string}</td>
                  {[admin, security, developer, viewer].map((allowed, i) => (
                    <td key={i} className="px-4 py-2.5 text-center text-xs">
                      {allowed
                        ? <span className="text-green-600 font-bold">✓</span>
                        : <span className="text-stone-300 font-medium">—</span>
                      }
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="guard-onboarding">
        <SectionHeading id="guard-onboarding">Team onboarding</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          End-to-end flow for getting a team onto Guard. Each developer runs two commands, everything else is automatic.
        </p>

        <div className="space-y-0">
          {[
            { step: "1", title: "Admin installs Guard",          body: "Settings → Modules → ConductGuard → Install. Guard is provisioned with 18 starter policies. The admin shares the invite code or adds team members directly." },
            { step: "2", title: "Invite your team",              body: "Guard → Members → Invite. Assign roles: Developer for engineers, Security for security team, Viewer for stakeholders." },
            { step: "3", title: "Developer generates an API key",body: "Settings → API Keys → Generate key. Admin and Developer roles can generate keys. The key is tied to their workspace and role." },
            { step: "4", title: "Developer logs in",             body: "One command installs Guard, downloads policies, registers the hook in Claude Code and Codex, and registers the MCP server in Cursor and Windsurf.", code: "pip install conduct-cli\nconduct login --server https://api.conductai.ai --api-key cond_live_xxxx" },
            { step: "5", title: "Guard enforces from this moment",body: "Every AI tool call on the developer's machine is intercepted and checked against workspace policies. All activity, allowed and blocked, appears in the Guard dashboard." },
          ].map(({ step, title, body, code }) => (
            <div key={step} className="flex gap-6 pb-8 relative">
              <div className="flex flex-col items-center">
                <div className="w-8 h-8 rounded-full bg-stone-900 text-white text-sm font-bold flex items-center justify-center shrink-0 z-10">{step}</div>
                {parseInt(step) < 5 && <div className="w-px flex-1 bg-stone-200 mt-2" />}
              </div>
              <div className="pt-1 pb-2 flex-1">
                <p className="font-semibold text-stone-900 mb-1">{title}</p>
                <p className="text-sm text-stone-600 leading-relaxed mb-2">{body}</p>
                {code && <pre className="bg-stone-900 text-stone-100 rounded-lg px-4 py-3 text-xs font-mono mt-2 overflow-x-auto">{code}</pre>}
              </div>
            </div>
          ))}
        </div>

        <SubHeading>Keeping Guard current</SubHeading>
        <Pre>{`# After an admin updates policies:
conduct guard sync

# Check what's enforced right now:
conduct guard status

# See recent activity:
conduct guard audit --since 7d`}</Pre>

        <div className="mt-4 rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-700">
          <strong>CLI auto-updates.</strong> Developers never need to manually upgrade, the CLI checks PyPI on
          every run and upgrades itself if a newer version is available.
        </div>
      </section>

      <section id="guard-scenarios">
        <SectionHeading id="guard-scenarios">Test scenarios</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Four end-to-end scenarios that cover every Guard enforcement path. Run them in order after onboarding a developer to verify the full stack, hook, API, Slack, and activity log, is wired correctly.
        </p>

        <Screenshot
          src="/guard-docs/dashboard.png"
          alt="Guard dashboard showing active developers, events, tokens, and cost trend chart"
          caption="Guard dashboard, real-time overview of team AI usage. The cost trend chart breaks down spend by Claude vs Codex."
        />
        <Screenshot
          src="/guard-docs/activity-log.png"
          alt="Guard activity log showing tool calls from Claude Code and Codex with token counts"
          caption="Activity log, every tool call is recorded: who, which AI tool, what command, and token cost. Both Claude Code and Codex sessions appear here."
        />

        {/* Scenario 1 */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-7 h-7 rounded-full bg-stone-900 text-white text-xs font-bold flex items-center justify-center shrink-0">1</span>
            <h3 className="font-semibold text-stone-900 text-base">Workspace hard cap, blocks all tool calls</h3>
          </div>
          <p className="text-sm text-stone-500 mb-4 ml-10">Verify that setting the workspace monthly budget below current spend blocks every subsequent tool call for all users.</p>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/spend-controls.png"
              alt="Spend Controls panel showing team monthly budget, per-developer limit, alert threshold, and hard cap"
              caption="Guard → Spend, set the Team monthly budget and Hard cap here. Enable 'Hard cap on' to block sessions at 100%."
            />
          </div>
          <div className="ml-10 rounded-xl border border-stone-200 divide-y divide-stone-100 mb-4">
            {[
              { label: "Set workspace budget below current spend", detail: "Guard → Spend → Team monthly budget → set to a value ≤ current spend → Save." },
              { label: "Sync and clear the cache", detail: "conduct guard sync && rm ~/.conductguard/budget_cache.json" },
              { label: "Verify the API", detail: 'GET /guard/spend/budget-check, expect { "hard_blocked": true }' },
              { label: "Test the hook", detail: `echo '{"tool_name":"bash","tool_input":{"command":"ls"},"session_id":"test"}' | python3.11 ~/.conductguard/hook.py\nExpected: exit 2 with budget block message` },
            ].map(({ label, detail }) => (
              <div key={label} className="px-4 py-3">
                <p className="text-xs font-semibold text-stone-700 mb-1">{label}</p>
                <pre className="text-xs text-stone-500 font-mono whitespace-pre-wrap leading-relaxed">{detail}</pre>
              </div>
            ))}
          </div>
          <div className="ml-10 mb-4">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">What it looks like in Claude Code (live session, 2026-06-05)</p>
            <Screenshot
              src="/guard-docs/budget-cap-bash-blocked.png"
              alt="Claude Code terminal showing ConductGuard budget hard cap blocking a bash tool call"
              caption="Every tool call. Bash, Read, Edit, is blocked until the budget is raised. The message surfaces inline before the tool runs."
            />
            <Screenshot
              src="/guard-docs/budget-cap-claude-blocked.png"
              alt="Claude Code response showing Guard budget hard cap hit and instructions to raise the workspace budget"
              caption="Claude Code itself reports the block. Guard stops the entire session cold, no workaround from inside the agent."
            />
          </div>
          <div className="ml-10 mb-4">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">Slack notification when the cap is hit (live, 2026-06-05)</p>
            <pre className="bg-stone-900 text-green-400 rounded-xl px-4 py-3 text-xs font-mono overflow-x-auto leading-relaxed">{`🛑 BUDGET CAP HIT by budget-hard-cap in claude-code
Developer: sudhi@b2bsphere.com
Your team's monthly AI budget of $500.00 has been reached.
New tool calls are paused until the limit is raised. Contact your security team.

🛑 BUDGET CAP HIT by budget-hard-cap in codex
Developer: sudhi@b2bsphere.com
Your team's monthly AI budget of $500.00 has been reached.
New tool calls are paused until the limit is raised. Contact your security team.`}</pre>
            <p className="text-xs text-stone-400 mt-2 leading-relaxed">
              The alert fires once per tool when the cap is first hit, not on every blocked call. Guard blocks <strong className="text-stone-600">all registered tools simultaneously</strong>: Claude Code, Codex, Cursor. Each fires its own notification so your security team knows which sessions are affected.
            </p>
          </div>
          <div className="ml-10 rounded-xl bg-stone-50 border border-stone-200 px-4 py-2.5 text-xs text-stone-500">
            <strong className="text-stone-700">Teardown:</strong> Raise the budget above current spend → Save. Run conduct guard sync &amp;&amp; rm ~/.conductguard/budget_cache.json.
          </div>
        </div>

        {/* Scenario 2 */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-7 h-7 rounded-full bg-stone-900 text-white text-xs font-bold flex items-center justify-center shrink-0">2</span>
            <h3 className="font-semibold text-stone-900 text-base">Per-developer hard cap, blocks one user</h3>
          </div>
          <p className="text-sm text-stone-500 mb-4 ml-10">Verify that a per-developer spend limit blocks tool calls for a specific user without affecting others.</p>
          <div className="ml-10 rounded-xl border border-stone-200 divide-y divide-stone-100 mb-4">
            {[
              { label: "Set per-developer limit below the user's spend", detail: "Guard → Spend → Default per-developer limit → set below current user spend → Save." },
              { label: "Sync and clear the cache", detail: "conduct guard sync && rm ~/.conductguard/budget_cache.json" },
              { label: "Verify the API with clerk_user_id", detail: "GET /guard/spend/budget-check?workspace_id=<ws>&clerk_user_id=<uid>\nExpect { \"hard_blocked\": true } for this user only." },
              { label: "Test the hook", detail: "Same hook test as Scenario 1, expect exit 2 with per-user block message." },
            ].map(({ label, detail }) => (
              <div key={label} className="px-4 py-3">
                <p className="text-xs font-semibold text-stone-700 mb-1">{label}</p>
                <pre className="text-xs text-stone-500 font-mono whitespace-pre-wrap leading-relaxed">{detail}</pre>
              </div>
            ))}
          </div>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/spend-by-developer.png"
              alt="Spend breakdown by developer and by AI tool showing sessions, tokens, cost, and budget"
              caption="Guard → Spend. By Developer table shows each user's sessions, token usage, cost, savings, and individual budget. By AI Tool breakdown shows Claude Code vs Codex split."
            />
          </div>
          <div className="ml-10 rounded-xl bg-stone-50 border border-stone-200 px-4 py-2.5 text-xs text-stone-500">
            <strong className="text-stone-700">Teardown:</strong> Raise the per-developer limit above the user's spend → Save. Sync and clear cache.
          </div>
        </div>

        {/* Scenario 3 */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-7 h-7 rounded-full bg-stone-900 text-white text-xs font-bold flex items-center justify-center shrink-0">3</span>
            <h3 className="font-semibold text-stone-900 text-base">Policy rule, blocks a specific tool call</h3>
          </div>
          <p className="text-sm text-stone-500 mb-4 ml-10">Verify that a Guard policy rule matches a pattern in a tool call, blocks it with a custom message, logs it to the activity feed, and fires a Slack notification.</p>
          <div className="ml-10 rounded-xl border border-stone-200 divide-y divide-stone-100 mb-4">
            {[
              { label: "Create the policy rule", detail: "Guard → Policies → Add rule\nRule ID: no-rm | Match tool: bash | Match pattern: rm | Action: block\nMessage: Deleting files is not allowed. Use git to revert changes instead." },
              { label: "Sync the policy", detail: "conduct guard sync" },
              { label: "Test the hook directly", detail: `echo '{"tool_name":"bash","tool_input":{"command":"rm -rf /tmp/test"},"session_id":"test"}' | python3.11 ~/.conductguard/hook.py; echo "exit: $?"` },
              { label: "Trigger from Claude Code", detail: "Ask Claude to run: bash -c 'rm -rf /tmp/test'\nExpected: PreToolUse hook error, tool call blocked inline." },
              { label: "Verify activity log", detail: "Guard → Activity, find the event. Confirm decision=blocked, rule_id=no-rm, tool_name=bash." },
            ].map(({ label, detail }) => (
              <div key={label} className="px-4 py-3">
                <p className="text-xs font-semibold text-stone-700 mb-1">{label}</p>
                <pre className="text-xs text-stone-500 font-mono whitespace-pre-wrap leading-relaxed">{detail}</pre>
              </div>
            ))}
          </div>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/block-claude-terminal.png"
              alt="Claude Code terminal showing PreToolUse hook blocking a bash command with ConductGuard error message"
              caption="Claude Code surfaces the block inline, the tool call never runs. The error shows the rule message exactly as configured in Guard → Policies."
            />
          </div>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/audit-blocked.png"
              alt="Audit log showing blocked bash commands with no-rm rule alongside allowed events"
              caption="Guard → Activity, blocked events are tagged in red with the rule ID. Allowed events show green. Every tool call, blocked or allowed, is recorded."
            />
          </div>
          <div className="ml-10 mb-4">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">Real Slack notifications from a live session (2026-06-02)</p>
            <Screenshot
              src="/guard-docs/slack-drop-table-block.png"
              alt="Slack message from ConductAI showing salessupport@organicsphere.com blocked by no-drop-table rule"
              caption="DROP TABLE blocked. Slack fires instantly with the developer email, rule ID, and policy message."
            />
            <Screenshot
              src="/guard-docs/slack-file-delete-block.png"
              alt="Slack showing multiple no-rm blocks for salessupport@organicsphere.com in rapid succession"
              caption="Multiple blocks in the same session, each blocked tool call fires its own Slack message in real time."
            />
            <Screenshot
              src="/guard-docs/Password-keys-compromise.png"
              alt="Slack message from ConductAI showing salessupport@organicsphere.com warned by no-hardcoded-secrets rule in claude-code"
              caption="Hardcoded secret detected. Guard warns the developer in Slack instantly with the rule ID and policy message. The developer email is always surfaced so managers know exactly who triggered the alert."
            />
            <p className="text-xs text-stone-400 mt-1 leading-relaxed">The block fires on every blocked call. Spend alerts are deduped per 5% increment, policy blocks are not deduped.</p>
          </div>
          <div className="ml-10 rounded-xl bg-stone-50 border border-stone-200 px-4 py-2.5 text-xs text-stone-500">
            <strong className="text-stone-700">Teardown:</strong> Guard → Policies → delete no-rm → Save. Run conduct guard sync.
          </div>
        </div>

        {/* Scenario 4 */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-7 h-7 rounded-full bg-stone-900 text-white text-xs font-bold flex items-center justify-center shrink-0">4</span>
            <h3 className="font-semibold text-stone-900 text-base">Alert threshold, fires Slack notification</h3>
          </div>
          <p className="text-sm text-stone-500 mb-4 ml-10">Verify that spend crossing the alert threshold triggers a Slack notification, deduped per 5% increment.</p>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/settings-notifications.png"
              alt="Guard Settings page showing Slack channel input and notification toggles for block/warn and budget threshold"
              caption="Guard → Settings, configure the Slack channel and toggle which events trigger notifications. Both toggles must be on to receive spend alerts and block notifications."
            />
          </div>
          <div className="ml-10 rounded-xl border border-stone-200 divide-y divide-stone-100 mb-4">
            {[
              { label: "Set alert threshold below current spend %", detail: "Guard → Spend → Alert threshold → set below current spend percentage → Save.\nExample: if spend is at 85% of budget, set threshold to 80%." },
              { label: "Trigger any tool call", detail: "In a Claude Code session, trigger any passing tool call (e.g. list files). The hook checks spend on every call." },
              { label: "Verify Slack", detail: "Expected: ⚠️ Guard spend alert (workspace-wide): $X.XX of $Y.YY used (Z%), alert threshold 80% reached" },
            ].map(({ label, detail }) => (
              <div key={label} className="px-4 py-3">
                <p className="text-xs font-semibold text-stone-700 mb-1">{label}</p>
                <pre className="text-xs text-stone-500 font-mono whitespace-pre-wrap leading-relaxed">{detail}</pre>
              </div>
            ))}
          </div>
          <div className="ml-10 mb-4">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">Real Slack output from a live session (2026-06-02)</p>
            <pre className="bg-stone-900 text-green-400 rounded-xl px-4 py-3 text-xs font-mono overflow-x-auto leading-relaxed">{`7:45 PM  ⚠️ Guard spend alert (workspace-wide): $25.05 of $30.00 used (83%), alert threshold 80% reached
7:50 PM  ⚠️ Guard spend alert (workspace-wide): $27.39 of $30.00 used (91%), alert threshold 80% reached
7:52 PM  ⚠️ Guard spend alert (workspace-wide): $28.60 of $30.00 used (95%), alert threshold 80% reached
7:53 PM  ⚠️ Guard spend alert (workspace-wide): $30.23 of $30.00 used (101%), alert threshold 80% reached`}</pre>
            <p className="text-xs text-stone-400 mt-2 leading-relaxed">Each line represents a distinct 5% band crossing. Alerts do not fire on every tool call.</p>
          </div>
          <div className="ml-10 rounded-xl bg-stone-50 border border-stone-200 px-4 py-2.5 text-xs text-stone-500">
            <strong className="text-stone-700">Teardown:</strong> Set alert threshold back to your preferred operational value (e.g. 80%) and save.
          </div>
        </div>

        <div className="rounded-xl border border-stone-200 overflow-hidden mt-4">
          <div className="bg-stone-50 border-b border-stone-200 px-4 py-2.5">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Known issues</p>
          </div>
          <table className="w-full text-sm">
            <tbody className="divide-y divide-stone-100">
              {[
                ["Budget cache TTL", "Changes to spend limits take up to 5 min to reflect", "rm ~/.conductguard/budget_cache.json"],
                ["Wrong Python binary", "Apple system Python has network restrictions, hook fails silently", "Re-run conduct guard sync (auto-detects Homebrew Python since v0.4.20)"],
                ["Missing clerk_user_id", "Per-user budget checks silently skipped", "Run conduct guard sync, added in v0.4.16"],
                ["Alert dedup", "Alerts fire once per 5% increment, won't re-fire in the same band", "Adjust spend or threshold to cross a new 5% boundary"],
              ].map(([issue, detail, fix]) => (
                <tr key={issue}>
                  <td className="px-4 py-3 text-xs font-medium text-stone-800 w-44 align-top">{issue}</td>
                  <td className="px-4 py-3 text-xs text-stone-500 align-top">{detail}</td>
                  <td className="px-4 py-3 text-xs font-mono text-stone-500 align-top">{fix}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
