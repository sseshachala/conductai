import { Pre, SectionHeading, SubHeading } from "./shared"

export function TabBlocks() {
  return (
    <div className="space-y-16">
      <section id="memory-block">
        <SectionHeading id="memory-block">Memory block</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          The Memory block gives agents a persistent knowledge store. A <strong>read</strong> block
          retrieves past summaries before a run; a <strong>write</strong> block records what was done after.
          On the next run the agent has full context of what it did before on that repo.
        </p>

        <SubHeading>Recommended block order</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          {[
            { block: "Trigger",          note: "Issue labeled, PR opened, cron, etc." },
            { block: "Memory (read)",    note: "Retrieves past summaries, available as {{recall.entries}} in the brain", amber: true },
            { block: "Fetch Issue",      note: "Gets fresh data from GitHub, Linear, etc." },
            { block: "Brain",            note: "Receives both the current task and recalled context" },
            { block: "Memory (write)",   note: "Records what was done, used by future runs", amber: true },
            { block: "Notify",           note: "Posts the outcome to Slack / email" },
          ].map(({ block, note, amber }) => (
            <div key={block} className={`flex items-start gap-4 px-4 py-2.5 border-b border-stone-100 last:border-0 ${amber ? "bg-amber-50" : ""}`}>
              <span className={`text-xs font-semibold w-44 shrink-0 mt-0.5 ${amber ? "text-amber-700" : "text-stone-700"}`}>{block}</span>
              <span className="text-xs text-stone-500">{note}</span>
            </div>
          ))}
        </div>

        <SubHeading>Configuration fields</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-32">Field</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-28">Values</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-sm">
              {[
                ["action",  "read | write",       "read retrieves past summaries before the brain runs. write stores the outcome after the run completes."],
                ["scope",   "repo | workspace",   "repo isolates memories per repository. workspace shares memories across all repos in the workspace for this playbook."],
                ["key",     "auto-set",            "Groups memories together. Auto-populated from scope. Read-only in the UI."],
                ["limit",   "number (default 5)", "read only. Maximum past summaries to retrieve. Returns the most semantically similar entries first."],
                ["summary", "template string",    "write only. What to store. Supports {{block_id.field}} refs. Example: Fixed {{fetch_issue.title}} via {{brain.approach}}"],
              ].map(([field, values, desc]) => (
                <tr key={field}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800 align-top">{field}</td>
                  <td className="px-4 py-3 text-xs text-stone-500 align-top whitespace-nowrap">{values}</td>
                  <td className="px-4 py-3 text-xs text-stone-500 leading-relaxed">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>YAML reference</SubHeading>
        <Pre>{`blocks:
  recall_context:
    type: memory
    action: read
    scope: repo
    key: "{{_trigger.repo_full_name}}"
    limit: 5
    next: fetch_issue

  record_outcome:
    type: memory
    action: write
    scope: repo
    key: "{{_trigger.repo_full_name}}"
    summary: |
      Issue #{{fetch_issue.issue_number}}: {{fetch_issue.title}}
      Fix: {{implement_fix.approach}}
    next: notify`}</Pre>

        <div className="mt-4 rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-700">
          <strong>No OpenAI key?</strong> Memory falls back to recency-based retrieval, the 5 most recent summaries
          instead of the most semantically similar. You lose similarity search but not the feature.
        </div>
      </section>

    </div>
  )
}
