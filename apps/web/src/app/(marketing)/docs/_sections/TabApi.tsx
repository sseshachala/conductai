import { Code, Endpoint, Pre, SectionHeading } from "./shared"

export function TabApi() {
  return (
    <div className="space-y-16">
      <section id="api-auth">
        <SectionHeading id="api-auth">API. Authentication</SectionHeading>
        <p className="text-stone-600 text-sm mb-4">All API requests require two headers.</p>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-5">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Header</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              <tr>
                <td className="px-4 py-3 font-mono text-xs text-stone-800">X-Api-Key</td>
                <td className="px-4 py-3 text-stone-500">Your <Code>cond_live_</Code> API key (from Settings → API Keys)</td>
              </tr>
              <tr>
                <td className="px-4 py-3 font-mono text-xs text-stone-800">X-Workspace-Id</td>
                <td className="px-4 py-3 text-stone-500">Your workspace UUID</td>
              </tr>
            </tbody>
          </table>
        </div>
        <Pre>{`curl https://api.conductai.ai/workflows \\
  -H "X-Api-Key: cond_live_xxxxxxxxxxxxxxxx" \\
  -H "X-Workspace-Id: <workspace-id>"`}</Pre>
      </section>

      <section id="api-workflows">
        <SectionHeading id="api-workflows">API. Workflows</SectionHeading>
        <p className="text-stone-500 text-sm mb-5">Manage and trigger agents.</p>

        <Endpoint method="GET" path="/workflows" desc="List all workflows in the workspace.">
          <Pre>{`[
  {
    "id": "53ab8977-...",
    "name": "Autopilot Quick",
    "status": "active",
    "playbook_slug": "autopilot-quick",
    "project_id": "a1b2c3d4-..."
  }
]`}</Pre>
        </Endpoint>

        <Endpoint method="GET" path="/workflows/{id}" desc="Get a workflow including its graph and current version." />

        <Endpoint method="POST" path="/workflows/{id}/trigger" desc="Fire a test trigger using the playbook's built-in test payload. Returns run_id immediately.">
          <Pre>{`curl -X POST https://api.conductai.ai/workflows/53ab8977-.../trigger \\
  -H "X-Api-Key: cond_live_xxx" \\
  -H "X-Workspace-Id: <workspace-id>" \\
  -d '{}'

# Response
{ "ok": true, "run_id": "b858c434-...", "max_turns": 20 }`}</Pre>
        </Endpoint>
      </section>

      <section id="api-runs">
        <SectionHeading id="api-runs">API. Runs</SectionHeading>
        <p className="text-stone-500 text-sm mb-5">Inspect and stream run results.</p>

        <Endpoint method="GET" path="/workflows/{id}/runs" desc="List all runs for a workflow." />

        <Endpoint method="GET" path="/workflows/{id}/runs/{run_id}" desc="Get a run including status, state, and metadata.">
          <Pre>{`{
  "id": "b858c434-...",
  "status": "succeeded",
  "triggered_by": "manual:test_trigger",
  "started_at": "2026-05-26T12:00:00Z",
  "completed_at": "2026-05-26T12:03:21Z"
}`}</Pre>
        </Endpoint>

        <Endpoint method="GET" path="/workflows/{id}/runs/{run_id}/stream" desc="Server-Sent Events stream of live run events. Closes with [DONE].">
          <Pre>{`const es = new EventSource(
  \`https://api.conductai.ai/workflows/\${id}/runs/\${runId}/stream\` +
  \`?token=\${clerkToken}&workspace_id=\${workspaceId}\`
)
es.onmessage = (e) => {
  if (e.data === "[DONE]") { es.close(); return }
  const event = JSON.parse(e.data)
  console.log(event.kind, event.block_id, event.payload)
}`}</Pre>
          <div className="mt-3 rounded-lg bg-stone-50 border border-stone-200 p-3">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">Event kinds</p>
            <div className="flex flex-wrap gap-1.5">
              {["block_started","block_completed","block_failed","block_skipped","brain_tool_call","run_completed","run_failed","run_paused"].map(k => (
                <Code key={k}>{k}</Code>
              ))}
            </div>
          </div>
        </Endpoint>

        <Endpoint method="POST" path="/workflows/{id}/runs/{run_id}/approve" desc="Approve or reject a paused run (human-in-the-loop).">
          <Pre>{`-d '{"decision": "approved", "approver": "alice"}'`}</Pre>
        </Endpoint>

        <Endpoint method="POST" path="/workflows/{id}/runs/{run_id}/cancel" desc="Cancel a running or pending run." />
      </section>

      <section id="api-keys">
        <SectionHeading id="api-keys">API. API Keys</SectionHeading>
        <p className="text-stone-500 text-sm mb-5">Manage programmatic access keys for your workspace.</p>

        <Endpoint method="POST" path="/workspaces/{id}/api-keys" desc="Generate a new API key. The plaintext key is returned once, store it immediately.">
          <Pre>{`curl -X POST https://api.conductai.ai/workspaces/<id>/api-keys \\
  -H "Authorization: Bearer <clerk-token>" \\
  -H "X-Workspace-Id: <id>" \\
  -d '{"name": "CI pipeline"}'

# Response
{
  "id": "...",
  "name": "CI pipeline",
  "key": "cond_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "key_prefix": "cond_live_xxxx",
  "created_at": "2026-05-26T12:00:00Z"
}`}</Pre>
        </Endpoint>
        <Endpoint method="GET"    path="/workspaces/{id}/api-keys"         desc="List all API keys (prefix and metadata only, plaintext is never returned again)." />
        <Endpoint method="DELETE" path="/workspaces/{id}/api-keys/{key_id}" desc="Revoke an API key immediately." />
      </section>
    </div>
  )
}
