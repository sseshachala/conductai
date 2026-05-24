import Link from "next/link"

export const metadata = { title: "Docs — Conduct AI" }

export default function DocsPage() {
  return (
    <div className="min-h-screen bg-stone-50">
      <header className="bg-white border-b border-stone-200 px-6 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <img src="/logo.png" alt="Conduct AI" className="h-8 w-auto" />
        </Link>
        <Link href="/dashboard" className="text-sm text-stone-500 hover:text-stone-900 transition-colors">
          Go to app →
        </Link>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-12 flex gap-12">

        {/* Sidebar nav */}
        <nav className="w-48 shrink-0 hidden md:block">
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-3">Getting started</p>
          <ul className="space-y-1 text-sm text-stone-600">
            <li><a href="#overview" className="hover:text-stone-900 transition-colors">Overview</a></li>
            <li><a href="#environments" className="hover:text-stone-900 transition-colors">Environments</a></li>
          </ul>
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mt-6 mb-3">Integrations</p>
          <ul className="space-y-1 text-sm text-stone-600">
            <li><a href="#github" className="hover:text-stone-900 transition-colors">GitHub</a></li>
            <li><a href="#slack" className="hover:text-stone-900 transition-colors">Slack</a></li>
            <li><a href="#linear" className="hover:text-stone-900 transition-colors">Linear</a></li>
            <li><a href="#email" className="hover:text-stone-900 transition-colors">Email</a></li>
          </ul>
        </nav>

        {/* Content */}
        <main className="flex-1 min-w-0 space-y-14">

          {/* Overview */}
          <section id="overview">
            <h1 className="text-2xl font-bold text-stone-900 mb-3">Documentation</h1>
            <p className="text-stone-600 leading-relaxed">
              Conduct AI lets you build and run AI agents that interact with your tools — GitHub, Slack, Linear, and more.
              Agents are configured on a canvas, scoped to an environment, and run on-demand or on a schedule.
            </p>
          </section>

          {/* Environments */}
          <section id="environments">
            <h2 className="text-lg font-semibold text-stone-900 mb-2">Environments</h2>
            <p className="text-stone-600 leading-relaxed mb-4">
              An environment is a named set of credentials (e.g. <code className="bg-stone-100 px-1 py-0.5 rounded text-sm">production</code>, <code className="bg-stone-100 px-1 py-0.5 rounded text-sm">staging</code>).
              You create environments in <strong>Settings → Environments</strong>, add your integration tokens inside them,
              then assign an environment to each agent on the canvas.
            </p>
            <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600">
              <li>Go to <strong>Settings → Environments</strong> and create an environment.</li>
              <li>Click the environment and connect your integrations (GitHub, Slack, etc.).</li>
              <li>Open an agent on the canvas, go to <strong>Settings</strong>, and assign the environment.</li>
            </ol>
          </section>

          {/* GitHub */}
          <section id="github">
            <h2 className="text-lg font-semibold text-stone-900 mb-1">GitHub</h2>
            <p className="text-stone-500 text-sm mb-4">Create branches, push commits, open and merge pull requests, trigger Actions.</p>

            <h3 className="text-sm font-semibold text-stone-700 mb-2">Creating a fine-grained Personal Access Token</h3>
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
                    ["Contents", "Read and write", "Create branches, push commits, read code"],
                    ["Pull requests", "Read and write", "Open, review, and merge PRs"],
                    ["Actions", "Read and write", "Trigger and monitor workflow runs"],
                    ["Metadata", "Read-only (required)", "Auto-granted, cannot be removed"],
                  ].map(([perm, access, use]) => (
                    <tr key={perm}>
                      <td className="px-4 py-3 font-medium text-stone-800">{perm}</td>
                      <td className="px-4 py-3">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                          access.includes("Read-only") ? "bg-stone-100 text-stone-500" : "bg-green-50 text-green-700"
                        }`}>{access}</span>
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

          {/* Slack */}
          <section id="slack">
            <h2 className="text-lg font-semibold text-stone-900 mb-1">Slack</h2>
            <p className="text-stone-500 text-sm mb-4">Post messages, send DMs, and send approval requests to channels.</p>

            <h3 className="text-sm font-semibold text-stone-700 mb-2">Getting a Bot Token</h3>
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
                    ["chat:write", "Post messages to channels"],
                    ["im:write", "Send direct messages"],
                    ["channels:read", "List channels to target"],
                    ["users:read", "Resolve user IDs for DMs"],
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
              <li>Click <strong>Install to Workspace</strong> and copy the <strong>Bot User OAuth Token</strong> (<code className="bg-stone-100 px-1 py-0.5 rounded">xoxb-…</code>).</li>
              <li>Paste it into the Slack Connect form in your environment.</li>
            </ol>
          </section>

          {/* Linear */}
          <section id="linear">
            <h2 className="text-lg font-semibold text-stone-900 mb-1">Linear</h2>
            <p className="text-stone-500 text-sm mb-4">Fetch issues, post comments, update issue status.</p>
            <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600">
              <li>Go to <strong>Linear → Settings → API → Personal API keys</strong>.</li>
              <li>Create a new key and copy it (<code className="bg-stone-100 px-1 py-0.5 rounded">lin_api_…</code>).</li>
              <li>Paste it into the Linear Connect form in your environment.</li>
            </ol>
            <p className="text-sm text-stone-500 mt-3">Personal API keys have access to everything your Linear account can access. Use a dedicated service account for production.</p>
          </section>

          {/* Email */}
          <section id="email">
            <h2 className="text-lg font-semibold text-stone-900 mb-1">Email</h2>
            <p className="text-stone-500 text-sm mb-4">Send notifications via Resend (recommended) or SendGrid.</p>

            <h3 className="text-sm font-semibold text-stone-700 mb-2">Resend (recommended)</h3>
            <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600 mb-6">
              <li>Go to <a href="https://resend.com" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">resend.com</a> and create an account.</li>
              <li>Add and verify your sending domain under <strong>Domains</strong>.</li>
              <li>Go to <strong>API Keys</strong> and create a key with <strong>Sending access</strong>.</li>
              <li>Paste it into the Email Connect form (<code className="bg-stone-100 px-1 py-0.5 rounded">re_…</code>).</li>
            </ol>

            <h3 className="text-sm font-semibold text-stone-700 mb-2">SendGrid (alternative)</h3>
            <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600">
              <li>Go to <strong>SendGrid → Settings → API Keys → Create API Key</strong>.</li>
              <li>Choose <strong>Restricted Access</strong> and enable <strong>Mail Send</strong>.</li>
              <li>Paste the key into the Email Connect form (<code className="bg-stone-100 px-1 py-0.5 rounded">SG.…</code>).</li>
            </ol>
          </section>

        </main>
      </div>
    </div>
  )
}
