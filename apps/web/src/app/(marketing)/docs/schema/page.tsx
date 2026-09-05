export const metadata = {
  title: "Guard Rule Schema — Docs | Conduct",
  description:
    "Conduct Guard rules speak two dialects: JSON at runtime, Cedar for portability. Bidirectional interchange, no lock-in.",
}

export default function GuardSchemaDocsPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-16 w-full">
      <div className="mb-2">
        <a href="/docs" className="text-sm text-stone-400 hover:text-stone-600 transition-colors">
          Docs
        </a>
        <span className="text-sm text-stone-300 mx-2">/</span>
        <span className="text-sm text-stone-600">Guard Rule Schema</span>
      </div>

      <h1 className="text-3xl font-bold text-stone-900 mt-6 mb-2">Guard Rule Schema v1</h1>
      <p className="text-stone-500 mb-4 leading-relaxed">
        Guard rules speak two dialects: <strong>JSON</strong> for runtime evaluation, <strong>Cedar</strong> for portability. Both are semantically equivalent. Import your existing Cedar policies from AWS Verified Permissions or any Cedar-consuming IAM stack. Export any Conduct pack back to Cedar. No proprietary lock-in.
      </p>

      <div className="flex gap-3 mb-10 flex-wrap">
        <a
          href="https://github.com/sseshachala/conductai/blob/main/schemas/conduct-guard-rule.v1.json"
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md border border-stone-300 text-sm text-stone-700 hover:bg-stone-50"
        >
          JSON Schema →
        </a>
        <a
          href="https://github.com/sseshachala/conductai/blob/main/docs/guard/schema.md"
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md border border-stone-300 text-sm text-stone-700 hover:bg-stone-50"
        >
          Full reference →
        </a>
        <a
          href="/packs"
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-stone-900 text-white text-sm hover:bg-stone-700"
        >
          Try the packs →
        </a>
      </div>

      <nav className="mb-10 border border-stone-200 rounded-xl px-5 py-4">
        <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-3">On this page</p>
        <ol className="flex flex-col gap-1.5 text-sm text-stone-600">
          <li><a href="#why-two" className="hover:text-indigo-600 transition-colors">Why two dialects</a></li>
          <li><a href="#example" className="hover:text-indigo-600 transition-colors">Same rule, two forms</a></li>
          <li><a href="#interchange" className="hover:text-indigo-600 transition-colors">Bidirectional interchange</a></li>
          <li><a href="#frameworks" className="hover:text-indigo-600 transition-colors">Framework tags</a></li>
        </ol>
      </nav>

      <section id="why-two" className="mb-12">
        <h2 className="text-xl font-bold text-stone-900 mb-3">Why two dialects</h2>
        <p className="text-stone-600 leading-relaxed mb-3">
          Different audiences read policies differently. Engineers want grep-friendly JSON that embeds cleanly in pack files. Auditors want human-readable Cedar with recognizable annotations. You want a promise: nothing here is stuck in a proprietary language.
        </p>
        <ul className="list-disc pl-6 text-stone-600 leading-relaxed space-y-1">
          <li><strong>Runtime evaluates JSON</strong> — every pack file under <code className="text-xs bg-stone-100 px-1.5 py-0.5 rounded">apps/api/app/modules/guard/skill_packs/*.json</code> ships as JSON.</li>
          <li><strong>Cedar is a view</strong> — rendered on demand from the same source. Auditors read it, security teams import policies from Cedar-native tools using it.</li>
          <li><strong>Bidirectional and lossless</strong> — round-trip a rule through Cedar and back with no information loss on schema v1.</li>
        </ul>
      </section>

      <section id="example" className="mb-12">
        <h2 className="text-xl font-bold text-stone-900 mb-3">Same rule, two forms</h2>
        <p className="text-stone-600 leading-relaxed mb-4">One PCI-DSS rule from the <code className="text-xs bg-stone-100 px-1.5 py-0.5 rounded">conduct-pci-dss</code> pack.</p>

        <h3 className="text-sm font-semibold text-stone-700 mb-2">JSON (runtime)</h3>
        <pre className="text-xs bg-stone-950 text-stone-100 rounded-lg p-4 overflow-x-auto mb-6">
{`{
  "id": "pci_pan_guard",
  "description": "Block card number patterns (PCI DSS Req 3)",
  "match_tool": "edit,write,bash",
  "match_pattern": "\\\\b4[0-9]{12}(?:[0-9]{3})?\\\\b|\\\\b5[1-5][0-9]{14}\\\\b",
  "action": "block",
  "message": "Card number detected — never log or store PANs in plaintext.",
  "severity": "critical",
  "frameworks": ["PCI_DSS:3.4", "SOC2:CC6.1", "GDPR:Art32"],
  "iso_control": "A.8.11"
}`}
        </pre>

        <h3 className="text-sm font-semibold text-stone-700 mb-2">Cedar (portable)</h3>
        <pre className="text-xs bg-stone-950 text-stone-100 rounded-lg p-4 overflow-x-auto mb-2">
{`@id("pci_pan_guard")
@description("Block card number patterns (PCI DSS Req 3)")
@message("Card number detected — never log or store PANs in plaintext.")
@severity("critical")
@iso_control("A.8.11")
@compliance("PCI_DSS:3.4", "SOC2:CC6.1", "GDPR:Art32")
forbid (
    principal is Agent,
    action in [Action::"edit", Action::"write", Action::"bash"],
    resource
)
when {
    context.prompt matches "\\\\b4[0-9]{12}(?:[0-9]{3})?\\\\b|\\\\b5[1-5][0-9]{14}\\\\b"
};`}
        </pre>
        <p className="text-xs text-stone-400 mb-2">
          Get the live Cedar rendering with <code className="text-xs bg-stone-100 px-1.5 py-0.5 rounded">GET /guard/registry/packs/&#123;slug&#125;/cedar</code> or click <strong>⤓ Cedar</strong> on any pack tile at <a className="text-indigo-600 hover:underline" href="/packs">/packs</a>.
        </p>
      </section>

      <section id="interchange" className="mb-12">
        <h2 className="text-xl font-bold text-stone-900 mb-3">Bidirectional interchange</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="border border-stone-200 rounded-xl p-5">
            <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-2">Cedar → Guard</p>
            <p className="text-sm text-stone-600 leading-relaxed mb-3">
              Import Cedar JSON policies from AWS Verified Permissions, Dogwood, or any Cedar-native IAM stack.
            </p>
            <code className="block text-xs bg-stone-100 rounded p-2 text-stone-700">POST /guard/registry/import-cedar</code>
          </div>
          <div className="border border-stone-200 rounded-xl p-5">
            <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-2">Guard → Cedar</p>
            <p className="text-sm text-stone-600 leading-relaxed mb-3">
              Render any installed pack as Cedar text — annotated with severity, ISO control, and compliance framework tags.
            </p>
            <code className="block text-xs bg-stone-100 rounded p-2 text-stone-700">GET /guard/registry/packs/&#123;slug&#125;/cedar</code>
          </div>
        </div>
      </section>

      <section id="frameworks" className="mb-16">
        <h2 className="text-xl font-bold text-stone-900 mb-3">Framework tags</h2>
        <p className="text-stone-600 leading-relaxed mb-4">
          The <code className="text-xs bg-stone-100 px-1.5 py-0.5 rounded">frameworks</code> array is free-form but conventionally uses these prefixes for compliance-surface parity.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-stone-200 text-left text-xs uppercase tracking-widest text-stone-500">
                <th className="py-2 pr-4">Prefix</th>
                <th className="py-2 pr-4">Example</th>
                <th className="py-2">Standard</th>
              </tr>
            </thead>
            <tbody className="text-stone-700">
              {[
                ["PCI_DSS:",         "PCI_DSS:3.4",           "PCI Data Security Standard"],
                ["SOC2:",            "SOC2:CC6.1",            "SOC 2 Trust Services Criteria"],
                ["ISO_27001:",       "ISO_27001:A.8.24",      "ISO 27001 Annex A"],
                ["ISO_42001:",       "ISO_42001:8.24",        "ISO 42001 (AI management)"],
                ["GDPR:",            "GDPR:Art32",            "GDPR article"],
                ["HIPAA:",           "HIPAA:164.308",         "HIPAA Security Rule"],
                ["NIST_AI_RMF:",     "NIST_AI_RMF:MG-2.6",    "NIST AI Risk Management Framework"],
                ["MITRE_ATLAS:",     "MITRE_ATLAS:AML.T0051", "MITRE ATLAS (adversarial ML)"],
                ["OWASP_AGENTIC:",   "OWASP_AGENTIC:A01",     "OWASP Agentic Top 10"],
                ["SR_11_7:",         "SR_11_7:V.A.1",         "Fed Reserve model risk"],
              ].map(([prefix, ex, std]) => (
                <tr key={prefix} className="border-b border-stone-100">
                  <td className="py-2 pr-4 font-mono text-xs">{prefix}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{ex}</td>
                  <td className="py-2">{std}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
