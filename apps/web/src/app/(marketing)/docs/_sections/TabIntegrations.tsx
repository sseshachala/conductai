import { marked } from "marked"
// @ts-expect-error - .md imported as raw string via webpack asset/source
import oidcSetupMd from "../../../../../../../docs/reference/oidc-setup.md"
import { Code, SectionHeading, SubHeading } from "./shared"

export function TabIntegrations() {
  return (
    <div className="space-y-16">
      <section id="oidc" className="scroll-mt-8 break-words [&_h2]:text-xl [&_h2]:font-bold [&_h2]:mb-4 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:mt-6 [&_h3]:mb-3 [&_p]:text-sm [&_p]:text-stone-600 [&_p]:leading-relaxed [&_p]:mb-3 [&_ul]:text-sm [&_ul]:text-stone-600 [&_ul]:list-disc [&_ul]:ml-5 [&_ul]:mb-3 [&_li]:mb-2 [&_code]:font-mono [&_code]:text-xs [&_code]:break-all [&_table]:w-full [&_table]:table-fixed [&_table]:text-sm [&_table]:mb-4 [&_th]:text-left [&_th]:p-2 [&_th]:border-b [&_td]:p-2 [&_td]:border-b [&_td]:align-top"
        dangerouslySetInnerHTML={{ __html: marked.parse(oidcSetupMd, { async: false }) as string }}
      />
      <section id="github">
        <SectionHeading id="github">GitHub</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">Create branches, push commits, open and merge pull requests, trigger Actions.</p>

        <SubHeading>Creating a fine-grained Personal Access Token</SubHeading>
        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600 mb-6">
          <li>Go to <strong>GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens</strong>.</li>
          <li>Click <strong>Generate new token</strong>.</li>
          <li>Under <strong>Repository access</strong>, select the repos your agents will work with.</li>
          <li>Under <strong>Permissions</strong>, set the following:</li>
        </ol>

        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Permission</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Access</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Needed for</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["Contents",     "Read and write",          "Create branches, push commits, read code"],
                ["Pull requests","Read and write",          "Open, review, and merge PRs"],
                ["Actions",      "Read and write",          "Trigger and monitor workflow runs"],
                ["Metadata",     "Read-only (required)",    "Auto-granted, cannot be removed"],
              ].map(([perm, access, use]) => (
                <tr key={perm}>
                  <td className="px-4 py-3 font-medium text-stone-800">{perm}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${access.includes("Read-only") ? "bg-stone-100 text-stone-500" : "bg-green-50 text-green-700"}`}>{access}</span>
                  </td>
                  <td className="px-4 py-3 text-stone-500">{use}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
          <strong>Note:</strong> Fine-grained tokens are repo-scoped. If your agents work across multiple repos,
          either grant access to all repositories or create one token per repo group.
        </div>
      </section>

      <section id="slack">
        <SectionHeading id="slack">Slack</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">Post messages, send DMs, and send approval requests to channels.</p>

        <SubHeading>Getting a Bot Token</SubHeading>
        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600 mb-4">
          <li>Go to <a href="https://api.slack.com/apps" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">api.slack.com/apps</a> and create a new app (from scratch).</li>
          <li>Under <strong>OAuth & Permissions</strong>, add these Bot Token Scopes:</li>
        </ol>

        <div className="rounded-xl border border-stone-200 overflow-hidden mb-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Scope</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Needed for</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["chat:write",   "Post messages to channels"],
                ["im:write",     "Send direct messages"],
                ["channels:read","List channels to target"],
                ["users:read",   "Resolve user IDs for DMs"],
              ].map(([scope, use]) => (
                <tr key={scope}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800">{scope}</td>
                  <td className="px-4 py-3 text-stone-500">{use}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600" start={3}>
          <li>Click <strong>Install to Workspace</strong> and copy the <strong>Bot User OAuth Token</strong> (<Code>xoxb-…</Code>).</li>
          <li>Paste it into the Slack Connect form in your environment.</li>
        </ol>
      </section>

      <section id="linear">
        <SectionHeading id="linear">Linear</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">Fetch issues, post comments, update issue status.</p>
        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600">
          <li>Go to <strong>Linear → Settings → API → Personal API keys</strong>.</li>
          <li>Create a new key and copy it (<Code>lin_api_…</Code>).</li>
          <li>Paste it into the Linear Connect form in your environment.</li>
        </ol>
        <p className="text-sm text-stone-500 mt-3">Personal API keys have access to everything your Linear account can access. Use a dedicated service account for production.</p>
      </section>

      <section id="email">
        <SectionHeading id="email">Email</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">Send notifications via Resend (recommended) or SendGrid.</p>

        <SubHeading>Resend (recommended)</SubHeading>
        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600 mb-6">
          <li>Go to <a href="https://resend.com" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">resend.com</a> and create an account.</li>
          <li>Add and verify your sending domain under <strong>Domains</strong>.</li>
          <li>Go to <strong>API Keys</strong> and create a key with <strong>Sending access</strong>.</li>
          <li>Paste it into the Email Connect form (<Code>re_…</Code>).</li>
        </ol>

        <SubHeading>SendGrid (alternative)</SubHeading>
        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600">
          <li>Go to <strong>SendGrid → Settings → API Keys → Create API Key</strong>.</li>
          <li>Choose <strong>Restricted Access</strong> and enable <strong>Mail Send</strong>.</li>
          <li>Paste the key into the Email Connect form (<Code>SG.…</Code>).</li>
        </ol>
      </section>
    </div>
  )
}
