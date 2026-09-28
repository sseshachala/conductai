import type { Metadata } from "next"

const title = "Discover your AI tools. See what's actually verified."
const description = "Use conduct guard discover to distinguish installed AI tools, configured hooks, observed activity, and Conduct Gateway connectivity. Configuration is not proof of enforcement."

export const metadata: Metadata = {
  title: `${title} | Conduct`,
  description,
  alternates: { canonical: "https://conductai.ai/blog/conduct-guard-discover" },
  openGraph: {
    title,
    description,
    type: "article",
    url: "https://conductai.ai/blog/conduct-guard-discover",
    publishedTime: "2026-09-27T00:00:00-05:00",
  },
}

const output = `Gateway check uses the CLI credential; it does not prove this tool's inference traffic.

Discovery: 4 local findings (complete)
  claude-code [installed] | hooks: observed | gateway: unverified
  codex [running] | hooks: observed | gateway: unavailable
  cursor [running] | hooks: unverified | gateway: unverified
  copilot-cli [running] | hooks: configured | gateway: unverified
Configuration is not proof of enforcement. Run conduct guard sync for supported tool setup.`

export default function BlogPost() {
  return (
    <article className="max-w-3xl min-w-0 mx-auto px-6 py-16 text-stone-700 leading-relaxed">
      <header className="mb-10">
        <p className="text-sm text-stone-500 mb-4">Product updates · <time dateTime="2026-09-27">September 27, 2026</time></p>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-6">{title}</h1>
        <p className="text-lg">Installing an AI coding tool is easy. Knowing whether its actions are governed is harder.</p>
      </header>
      <div className="space-y-6 [&_h2]:text-2xl [&_h2]:font-bold [&_h2]:text-stone-900 [&_h2]:pt-6 [&_code]:break-words">
        <p>A configuration file can show that hooks are installed. A Gateway URL can show that routing is configured. Neither proves that a tool&apos;s actions or model requests are passing through those controls.</p>
        <p>That distinction is central to <strong>Conduct Guard Discovery</strong>.</p>

        <h2>Start with one command</h2>
        <pre className="bg-stone-950 text-stone-100 rounded-lg p-5 overflow-x-auto text-sm"><code>conduct guard discover</code></pre>
        <p>Discovery checks supported local tools, reports configuration and observed hook activity, and checks configured Conduct Gateway connections. Here is an actual example:</p>
        <pre aria-label="Example discovery output" tabIndex={0} className="bg-stone-950 text-stone-100 rounded-lg p-5 overflow-x-auto text-sm leading-relaxed"><code>{output}</code></pre>
        <p>This is not an &quot;everything is protected&quot; badge. It is a breakdown of what Conduct found and what evidence is available.</p>

        <h2>Read the evidence, not just the configuration</h2>
        <p>Each finding separates three questions:</p>
        <dl className="space-y-4">
          <div><dt className="font-semibold text-stone-900">Detection</dt><dd>Was the tool detected as installed or running at scan time?</dd></div>
          <div><dt className="font-semibold text-stone-900">Hooks</dt><dd>Are hooks configured, or has recent installation-linked hook activity been observed?</dd></div>
          <div><dt className="font-semibold text-stone-900">Gateway</dt><dd>Is routing configured, and could a supported connection check verify authentication and connectivity?</dd></div>
        </dl>
        <ul className="list-disc pl-6 space-y-3">
          <li><strong>Claude Code:</strong> Recent hook activity was observed. Gateway routing remains unverified.</li>
          <li><strong>Codex:</strong> The tool was running and hook activity was observed. The Gateway connection check was unavailable, so it did not establish a verified connection.</li>
          <li><strong>Cursor:</strong> The tool was running, but hook and Gateway evidence remain unverified.</li>
          <li><strong>Copilot CLI:</strong> Hooks are configured, but configuration alone does not show that a hook has executed.</li>
        </ul>
        <p><strong>&quot;Complete&quot; describes the discovery scan, not complete governance coverage.</strong> Observed hook activity is evidence of a reported event, not proof of continuous enforcement.</p>

        <h2>Gateway checks are included</h2>
        <p>Conduct CLI <a className="underline" href="https://github.com/sseshachala/conductai/releases/tag/cli/v0.14.15">0.14.15</a> includes Gateway connection verification in discovery by default.</p>
        <p>For supported, configured Conduct endpoints, the check uses the CLI&apos;s Conduct credential to make a model-list request. It does not send prompts, make paid inference calls, or test an upstream provider API key.</p>
        <p>A successful check establishes connectivity with that credential. <strong>It does not prove that the discovered tool sends its inference traffic through Gateway.</strong> These checks do not verify external gateways such as LiteLLM or OpenRouter.</p>
        <p>To skip the connection check:</p>
        <pre className="bg-stone-950 text-stone-100 rounded-lg p-5 overflow-x-auto text-sm"><code>conduct guard discover --no-verify-gateway</code></pre>

        <h2>Turn findings into next steps</h2>
        <p>For supported tools that need setup, run:</p>
        <pre className="bg-stone-950 text-stone-100 rounded-lg p-5 overflow-x-auto text-sm"><code>conduct guard sync</code></pre>
        <p>Restart the affected tool, perform a simple tool action, then run discovery again. Look for hook status to move from <strong>configured</strong> to <strong>observed</strong>.</p>
        <p>In Conduct&apos;s <strong>Guard → Agents Discovered</strong> view, inspect installation evidence, timestamps, and setup guidance, then open Flight Recorder to investigate recorded activity.</p>
        <p>If Gateway remains unavailable or unverified, investigate that separately. Reinstalling hooks is not proof that model routing works.</p>

        <h2>Configuration is a starting point</h2>
        <p>AI governance needs more than an inventory of installed tools. It needs a clear distinction between what was discovered, what is configured, what has been observed, and what still needs verification.</p>
        <p>Conduct Guard Discovery makes those distinctions visible, without turning missing evidence into a claim of protection.</p>
        <p><strong>Start with <code>conduct guard discover</code>. See what&apos;s known. Verify what&apos;s next.</strong></p>
        <p><a href="/tools/conduct-cli" className="underline font-semibold">Install the Conduct CLI</a></p>
      </div>
      <footer className="mt-12 pt-6 border-t border-stone-200"><a href="/blog" className="underline text-sm">All posts</a></footer>
    </article>
  )
}
