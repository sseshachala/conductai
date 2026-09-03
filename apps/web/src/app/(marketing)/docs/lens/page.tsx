export const metadata = {
  title: "Lens — Docs | Conduct",
  description: "Lens is the conversational chat surface built into the Conduct app for querying Guard status, playbooks, and evidence.",
}

export default function LensDocsPage() {
  return (
    <div className="max-w-2xl mx-auto px-6 py-16 w-full">
      <div className="mb-2">
        <a href="/docs" className="text-sm text-stone-400 hover:text-stone-600 transition-colors">
          Docs
        </a>
        <span className="text-sm text-stone-300 mx-2">/</span>
        <span className="text-sm text-stone-600">Lens</span>
      </div>

      <h1 className="text-3xl font-bold text-stone-900 mt-6 mb-2">Lens</h1>
      <p className="text-stone-500 mb-10 leading-relaxed">
        Lens is the conversational interface built into the Conduct app. It is not a standalone product or a separate chat service — it is the in-app surface for querying Guard activity, playbook state, and evidence records.
      </p>

      <nav className="mb-10 border border-stone-200 rounded-xl px-5 py-4">
        <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-3">On this page</p>
        <ol className="flex flex-col gap-1.5 text-sm text-stone-600">
          <li><a href="#overview" className="hover:text-indigo-600 transition-colors">Overview</a></li>
          <li><a href="#tool-inventory" className="hover:text-indigo-600 transition-colors">Tool inventory</a></li>
          <li><a href="#access" className="hover:text-indigo-600 transition-colors">Accessing Lens</a></li>
        </ol>
      </nav>

      <section id="overview" className="mb-10">
        <h2 className="text-xl font-bold text-stone-900 mb-3">Overview</h2>
        <p className="text-stone-600 leading-relaxed">
          Lens lives inside the Conduct workspace. Developers and security teams use it to ask questions about live Guard state, run lookups across the audit trail, inspect playbook runs, and surface spend data — all without leaving the app. Responses are grounded in workspace data, not trained knowledge.
        </p>
      </section>

      <section id="tool-inventory" className="mb-10">
        <h2 className="text-xl font-bold text-stone-900 mb-3">Tool inventory</h2>
        <p className="text-stone-600 leading-relaxed mb-4">
          Lens is backed by a registry of workspace-scoped tools. Each tool resolves live data from the API rather than from the language model&apos;s weights. The current registry covers:
        </p>
        <ul className="flex flex-col gap-2 text-sm text-stone-600 list-disc pl-5">
          <li>Guard status and recent activity (blocks, warnings, approvals)</li>
          <li>Playbook run history and block-level event log</li>
          <li>Evidence records and hash-chain verification</li>
          <li>Spend and token usage by agent and workspace</li>
          <li>Credential and environment status</li>
        </ul>
        <p className="text-stone-400 text-sm mt-4">Full tool schema reference: see the source registry at <code className="bg-stone-100 px-1 rounded text-xs">apps/api/app/modules/lens/</code>.</p>
      </section>

      <section id="access" className="mb-10">
        <h2 className="text-xl font-bold text-stone-900 mb-3">Accessing Lens</h2>
        <p className="text-stone-600 leading-relaxed">
          Lens is available to all workspace members with at least viewer role. Open the Conduct app and select <strong>Lens</strong> from the left-hand navigation. There is no separate login or API key — Lens inherits your workspace session.
        </p>
      </section>

      <div className="border-t border-stone-100 pt-6 mt-6">
        <a
          href="https://github.com/sseshachala/conductai/tree/main/apps/api/app/modules/lens"
          className="text-sm text-indigo-600 hover:text-indigo-800 transition-colors font-medium"
          target="_blank"
          rel="noopener noreferrer"
        >
          View Lens source on GitHub
        </a>
      </div>
    </div>
  )
}
