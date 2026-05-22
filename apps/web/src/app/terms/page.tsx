import Link from "next/link"

export const metadata = { title: "Terms of Service — Conduct" }

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-stone-50">
      <div className="max-w-2xl mx-auto px-6 py-16">
        <Link href="/" className="text-xs text-stone-400 hover:text-stone-700 transition-colors mb-8 inline-block">← Back to Conduct</Link>
        <h1 className="text-2xl font-bold text-stone-900 mb-2">Terms of Service</h1>
        <p className="text-xs text-stone-400 mb-10">Last updated: May 2025</p>
        <div className="prose prose-stone prose-sm max-w-none space-y-6 text-stone-600 leading-relaxed">
          <section>
            <h2 className="text-base font-semibold text-stone-800 mb-2">Acceptance</h2>
            <p>By using Conduct, you agree to these terms. If you are using Conduct on behalf of an organization, you represent that you have authority to bind that organization.</p>
          </section>
          <section>
            <h2 className="text-base font-semibold text-stone-800 mb-2">Use of the service</h2>
            <p>You may use Conduct to automate engineering workflows within your organization. You are responsible for the agents and workflows you create, including any actions they take on external systems (GitHub, Slack, etc.) using credentials you provide.</p>
          </section>
          <section>
            <h2 className="text-base font-semibold text-stone-800 mb-2">Acceptable use</h2>
            <p>You may not use Conduct to violate any laws, infringe third-party rights, send spam, or perform unauthorized access to systems. We reserve the right to suspend accounts that violate these terms.</p>
          </section>
          <section>
            <h2 className="text-base font-semibold text-stone-800 mb-2">Open source</h2>
            <p>The Conduct codebase is available under the MIT license at <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="text-stone-900 underline hover:no-underline">github.com/sseshachala/conductai</a>. Self-hosted deployments are your responsibility.</p>
          </section>
          <section>
            <h2 className="text-base font-semibold text-stone-800 mb-2">Limitation of liability</h2>
            <p>Conduct is provided "as is" without warranties of any kind. We are not liable for any damages arising from your use of the service, including any actions taken by agents you configure.</p>
          </section>
          <section>
            <h2 className="text-base font-semibold text-stone-800 mb-2">Changes</h2>
            <p>We may update these terms from time to time. Continued use of the service after changes constitutes acceptance.</p>
          </section>
          <section>
            <h2 className="text-base font-semibold text-stone-800 mb-2">Contact</h2>
            <p>Questions? Email us at <a href="mailto:hello@conductagentic.com" className="text-stone-900 underline hover:no-underline">hello@conductagentic.com</a>.</p>
          </section>
        </div>
      </div>
    </div>
  )
}
