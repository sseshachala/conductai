export const metadata = {
  title: "Cedar can't say \"warn\". Here's why we shipped our own schema. | Conduct",
  description:
    "We support AWS Cedar first because it is the largest existing base of policies teams already have. We didn't stop at Cedar because Cedar-only means AWS-only. Here's the honest audit: what we adopted, what Cedar can't express, and how the same schema roundtrips to OPA, Kyverno, and Sentinel next.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Positioning
          </span>
          <span className="text-xs text-stone-400">September 7, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          Cedar can&rsquo;t say &ldquo;warn&rdquo;.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          We support AWS Cedar first — because Verified Permissions
          is the largest existing base of policies teams already
          have, and Cedar is the most permissively-licensed modern
          policy language. But we didn&rsquo;t stop at Cedar because{" "}
          <strong>Cedar-only means AWS-only</strong>. Here is the
          honest audit: what we adopted, what Cedar can&rsquo;t
          express without inventing conventions it was designed to
          prevent, and how the same schema roundtrips to OPA,
          Kyverno, and Sentinel next.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">
        <p className="text-stone-700 leading-relaxed mb-6">
          When you ship a policy schema in 2026, you get one question:{" "}
          <em>why didn&rsquo;t you just use Cedar?</em>
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          It is the right question. Cedar is excellent at authorization.
          AWS is pushing it hard. Verified Permissions is real. The
          ecosystem is growing. Anyone building a policy layer in the
          same year without a public reason to fork the stack should be
          asked to defend the decision.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          So we ran the audit before we wrote a line of schema. Here
          is what we adopted, what we couldn&rsquo;t adopt, and the
          condition under which we&rsquo;d flip our own defaults.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          What we adopted verbatim
        </h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          The rule for this project was: invent nothing you can borrow.
        </p>
        <ul className="list-disc pl-6 mb-6 text-stone-700 leading-relaxed space-y-2">
          <li>
            <strong>JSON Schema 2020-12</strong> as the meta-format —
            so linters, IDEs, and CI validators just work.
          </li>
          <li>
            <strong>Cedar as a bidirectional interchange format.</strong>{" "}
            Any Conduct pack renders as annotated Cedar text; any
            Cedar policy from AWS Verified Permissions can be imported
            back in. Roundtrip is lossless on schema v1.
          </li>
          <li>
            <strong>
              MITRE ATLAS, OWASP Agentic Top 10, NIST AI RMF, ISO 42001,
              ISO 27001, PCI DSS, SOC 2, HIPAA, GDPR, and SR 11-7
            </strong>{" "}
            as tag prefixes on the <code>frameworks[]</code> array.
            Buyers already know these vocabularies. We use them
            unchanged.
          </li>
          <li>
            <strong>Namespaced annotations map</strong> so metadata
            from OPA, Kyverno, Cedar, or your own tooling roundtrips
            through Conduct without loss.
          </li>
        </ul>
        <p className="text-stone-700 leading-relaxed mb-6">
          That covers most of the surface. The remaining gap is where
          we had to author.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          Why AWS Cedar first among many
        </h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Of every existing policy language, we shipped the Cedar
          exporter first. Four reasons, none of them AWS loyalty:
        </p>
        <ul className="list-disc pl-6 mb-6 text-stone-700 leading-relaxed space-y-2">
          <li>
            <strong>Largest existing installed base.</strong> AWS
            Verified Permissions is the biggest managed policy service
            in production. If a customer already has policies, they
            most likely have them in Cedar. Making the roundtrip
            lossless means they don&rsquo;t have to rewrite anything
            to try us.
          </li>
          <li>
            <strong>Modern, purpose-built, permissive.</strong> Cedar
            is BSD-2-Clause open source, born in 2023 for the exact
            problem shape we care about — authorization decisions
            evaluated in milliseconds — not a legacy XML dialect
            (XACML) or a Turing-complete language pretending to be
            a schema (Rego).
          </li>
          <li>
            <strong>Annotation model roundtrips cleanly.</strong>{" "}
            Cedar&rsquo;s <code>@annotation</code> mechanism maps
            one-to-one with our namespaced annotations map. Metadata
            crosses the boundary without loss. OPA package comments
            and Kyverno labels do not have this property natively —
            they need bespoke serialization.
          </li>
          <li>
            <strong>AWS Bedrock AgentCore is investing here.</strong>{" "}
            AWS is actively pushing Cedar as the policy layer for
            agent scenarios. If any incumbent ships first-class agent
            primitives in the next 18 months, it will be them. Being
            in-lane with that gravity is worth more than pretending
            it isn&rsquo;t happening.
          </li>
        </ul>
        <p className="text-stone-700 leading-relaxed mb-6">
          That is why Cedar first. It is not why Cedar only.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          Why not Cedar-only
        </h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Every policy language ships with an implicit cloud
          alignment. Cedar-only means AWS-only. That is a bet not
          every buyer wants to make, and honestly not one we want to
          make either. The other ecosystems are load-bearing for real
          teams:
        </p>
        <ul className="list-disc pl-6 mb-6 text-stone-700 leading-relaxed space-y-2">
          <li>
            <strong>OPA / Rego</strong> runs Kubernetes admission,
            service mesh policy, and API gateways across every cloud.
          </li>
          <li>
            <strong>Kyverno</strong> is the Kubernetes-native
            admission standard for teams that want YAML instead of
            Rego.
          </li>
          <li>
            <strong>HashiCorp Sentinel</strong> owns Terraform
            pre-apply policy. If your infra pipeline gates on
            Sentinel, your agent&rsquo;s Terraform changes need to
            speak that dialect.
          </li>
          <li>
            <strong>XACML</strong> still lives in older enterprise
            IAM stacks. Legacy, but real.
          </li>
        </ul>
        <p className="text-stone-700 leading-relaxed mb-6">
          The good news: the roundtrip machinery already exists. Our
          namespaced annotations map is designed to carry OPA,
          Kyverno, and Cedar metadata simultaneously without loss. The
          export engines are a shipping question, not a design
          question. Each is a two- to three-week engineering project
          when a real customer asks. Cedar shipped first; the others
          ship on demand.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          The mapping table on{" "}
          <a href="/docs/schema#mapping" className="text-indigo-600 hover:underline">
            /docs/schema
          </a>{" "}
          walks every concept — rule id, decision, actor, resource,
          match condition, severity, compliance, metadata, enforcement
          point — across all six policy languages. Every field we ship
          has a corresponding field in at least three of them. The
          category is new. The vocabulary isn&rsquo;t.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          Five things Cedar cannot express
        </h2>
        <p className="text-stone-700 leading-relaxed mb-6">
          Cedar 4.5 is still principal / action / resource with{" "}
          <code>permit</code> and <code>forbid</code>. Excellent scope
          for authorization. Wrong scope for agentic tool-call policy.
          Here is what breaks when you try to force-fit it.
        </p>

        <h3 className="text-xl font-semibold text-stone-900 mt-8 mb-3">
          1. Non-binary decisions
        </h3>
        <p className="text-stone-700 leading-relaxed mb-6">
          Agentic policy needs at least four decisions beyond{" "}
          <em>allow</em>. <strong>warn</strong> proceeds but flags.{" "}
          <strong>inject</strong> prepends context to the prompt.{" "}
          <strong>audit</strong> records without deciding.{" "}
          <strong>approval</strong> pauses the run until a human
          answers. Encoding these as Cedar obligations pushes
          semantics <em>out</em> of the policy language and into
          runtime convention — the exact anti-pattern Cedar was
          designed to prevent.
        </p>

        <h3 className="text-xl font-semibold text-stone-900 mt-8 mb-3">
          2. Free-text pattern matching
        </h3>
        <p className="text-stone-700 leading-relaxed mb-6">
          Cedar&rsquo;s <code>like</code> is glob, not regex. Its
          condition grammar targets structural attribute checks, not
          scanning LLM prompts for card numbers, secrets, or PII.
          Regex over <code>tool_input.prompt</code> is our common case.
          Wedging it into Cedar loses linter and IDE support without
          giving you a stronger primitive in return.
        </p>

        <h3 className="text-xl font-semibold text-stone-900 mt-8 mb-3">
          3. Enforcement-surface metadata
        </h3>
        <p className="text-stone-700 leading-relaxed mb-6">
          Every Conduct rule declares which of four surfaces —
          proxy, pre-tool hook, MCP <code>guard_check</code>, workflow
          runtime — can hard-block it versus advise it. Cedar assumes
          one PDP. It has no concept of &ldquo;which enforcement point
          evaluates me.&rdquo; That metadata is load-bearing for us:
          it tells buyers where a rule can actually stop something
          versus where it can only tell them after.
        </p>

        <h3 className="text-xl font-semibold text-stone-900 mt-8 mb-3">
          4. Compliance frameworks as searchable fields
        </h3>
        <p className="text-stone-700 leading-relaxed mb-6">
          Auditors ask &ldquo;show me every rule tagged{" "}
          <code>NIST_AI_RMF:MG-2.6</code>.&rdquo; Cedar can carry that
          as <code>@annotation</code>, but annotations are opaque
          strings — no schema, no validation, no searchable field.
          Our <code>frameworks[]</code> array is queryable by
          construction. It matters because the compliance surface is
          how these packs get sold.
        </p>

        <h3 className="text-xl font-semibold text-stone-900 mt-8 mb-3">
          5. The pack container
        </h3>
        <p className="text-stone-700 leading-relaxed mb-6">
          Cedar policies are individual documents. What we ship are{" "}
          <em>bundles</em> — slug, version, tier, UI hints, rules
          array. Pack-as-unit is what customers install, version, and
          publish. Cedar has no equivalent.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          The one-liner
        </h2>
        <div className="bg-stone-50 border border-stone-200 rounded-xl p-6 my-6">
          <p className="text-stone-800 leading-relaxed text-lg">
            <strong>
              Cedar is the right <em>interchange</em> format. It is not
              the right <em>authoring</em> format for agentic tool-call
              policy.
            </strong>
          </p>
        </div>
        <p className="text-stone-700 leading-relaxed mb-6">
          Interchange means: portability guarantee, escape hatch, no
          lock-in. Authoring means: what pack authors type, what CI
          validates, what customers install. We optimized each for its
          job.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          The flip condition
        </h2>
        <p className="text-stone-700 leading-relaxed mb-6">
          Standards move. If any of the ecosystems above — Cedar,
          OPA, Kyverno, Sentinel — ships first-class primitives for
          agentic tool calls (non-binary decisions, prompt content
          matchers, enforcement-surface metadata) before we do, we
          adopt their vocabulary and generate our JSON view from it.
          AWS is the most likely candidate given the Bedrock AgentCore
          investment, but we&rsquo;re not betting on a single vendor
          to define the category.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          Until then, this schema is the honest floor. It carries
          every concept the incumbents carry plus the four our
          category needs. It exports back to Cedar today, to OPA and
          Kyverno on request, to Sentinel when a Terraform-heavy
          customer asks. Nobody gets locked in — in either direction,
          to any vendor.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          What we&rsquo;re not claiming
        </h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          We are not building a general policy engine. Runtime
          enforcement stays Conduct-specific. What ships is a portable{" "}
          <em>representation</em> for a category none of the incumbents
          target: OPA/Rego is generic policy, Cedar is authorization,
          Kyverno is Kubernetes admission, Sentinel is Terraform. Ours
          is the shape between all of those — an agent invoking a
          tool.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          The mapping table on <a href="/docs/schema#mapping" className="text-indigo-600 hover:underline">/docs/schema</a>{" "}
          walks the concept-by-concept alignment across all six
          engines. Every field we ship has a corresponding field in at
          least three of them. The category is new. The vocabulary
          isn&rsquo;t.
        </p>

        <hr className="my-10 border-stone-200" />

        <div className="bg-stone-50 border border-stone-200 rounded-xl p-6 my-10">
          <p className="text-stone-700 leading-relaxed mb-4">
            <strong>See the full mapping.</strong>{" "}
            <a href="/docs/schema" className="text-indigo-600 font-semibold hover:underline">
              /docs/schema
            </a>{" "}
            has the same rule side-by-side in JSON and Cedar, the
            nine-dimension mapping table across OPA, Kyverno, Sentinel,
            Cedar, XACML, and MITRE ATLAS, and the full JSON Schema
            file for tooling.
          </p>
          <p className="text-stone-700 leading-relaxed mb-4">
            <strong>Try the packs.</strong> Every installed pack at{" "}
            <a href="/packs" className="text-indigo-600 font-semibold hover:underline">
              /packs
            </a>{" "}
            has a{" "}
            <strong>⤓ Cedar</strong>{" "}
            button on its tile — one click downloads the pack as{" "}
            <code>.cedar</code>. Import from Cedar-native stacks via{" "}
            <code>POST /guard/registry/import-cedar</code>.
          </p>
          <a
            href="/docs/schema"
            className="inline-block text-indigo-600 font-semibold hover:underline"
          >
            Read the schema docs →
          </a>
        </div>
      </div>
    </article>
  )
}
