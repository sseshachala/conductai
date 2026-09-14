export const metadata = {
  title: "The vendor is watching. Are you? | Conduct",
  description:
    "Anthropic's September 2026 threat report documents multi-agent kill chains run through stolen API keys. The vendor sees it because they sit in the middle of every request. Enterprises need the same vantage point on their side.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Positioning
          </span>
          <span className="text-xs text-stone-400">September 14, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          The vendor is watching. Are you?
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          A quick take on Anthropic&rsquo;s September 2026 threat report — and
          the uncomfortable half of it that every CISO should be asking about.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">
        <p className="text-stone-700 leading-relaxed mb-6">
          Anthropic just published the most useful enterprise-AI security
          document of the year, and almost no one is treating it that way.
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          The{" "}
          <a
            href="https://www.anthropic.com/news/detecting-countering-misuse-aug-2026"
            className="text-indigo-600 underline"
            target="_blank"
            rel="noreferrer"
          >
            September 2026 misuse report
          </a>{" "}
          covers eight months of threat activity Anthropic detected and
          disrupted on their own API. Seven harm categories. Suspected
          state-sponsored groups. Commercial spyware vendors. Financially
          motivated criminals. A hacktivist with a stolen API key running
          multi-victim campaigns that a year ago would have required a
          well-funded team.
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          Read the report as an operator and one line jumps out:
        </p>

        <blockquote className="border-l-4 border-stone-300 pl-4 italic text-stone-700 mb-6">
          &ldquo;Sophisticated attacks no longer require sophisticated
          attackers.&rdquo;
        </blockquote>

        <p className="text-stone-700 leading-relaxed mb-6">
          That is not a slogan. It is a load-bearing observation about labor
          economics. The floor of what one person with a laptop can do has
          moved. Case study GTG-20006 — attributed to Midnight Blizzard —
          describes a Russian operator running an AI-orchestrated kill chain
          against Ukrainian government, defense, and drone-supply-chain
          targets. Reconnaissance, phishing infrastructure, credential theft,
          malware that automatically rebuilds itself when defenders detect
          it. All of it stitched together by Claude Code skills the operator
          was refining in place.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          What Anthropic actually did
        </h2>

        <p className="text-stone-700 leading-relaxed mb-6">
          They watched the traffic. They saw the prompt patterns. They
          correlated tool calls across sessions. They banned the accounts.
          They notified authorities. They wrote it up.
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          They could do all of that for one reason:{" "}
          <strong>
            they sit in the middle of every request to their models.
          </strong>{" "}
          The vantage point is the point.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          The uncomfortable half of the report
        </h2>

        <p className="text-stone-700 leading-relaxed mb-6">
          The report is silent on the question every CISO should be asking:{" "}
          <em>when the API key in that case was stolen, whose was it?</em>
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          Anthropic can tell you a <code>sk-ant-*</code> key was abused. They
          cannot tell your legal team which of your developers pasted it into
          a public repo, which contractor still has it on a decommissioned
          laptop, which shadow agent on a designer&rsquo;s machine has been
          using it to summarise customer PII into a Google Doc. That
          visibility is not the vendor&rsquo;s job. It never was. The vendor
          protects the vendor.
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          If adversaries are already orchestrating multi-agent kill chains
          through <em>stolen enterprise keys</em> — and Anthropic just
          documented that they are — the mirror problem is unavoidable. Every
          organisation with more than a handful of developers has key sprawl.
          Most have zero inventory of the agents actually running on employee
          machines. And every one of those keys, every one of those agents,
          is now a potential entry point for exactly the workflows this
          report describes.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          Your own middle
        </h2>

        <p className="text-stone-700 leading-relaxed mb-6">
          The lesson from cloud is instructive. AWS did not solve the
          &ldquo;who did what with this credential&rdquo; problem by asking
          each service to log itself. They put IAM, CloudTrail, and org
          policies <em>in the middle of every API call</em>. That is what
          made governance possible. LLM vendors have not shipped that layer,
          and given competitive pressure, they are unlikely to ship the
          enterprise-facing version any time soon.
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          Which leaves the customer with two options:
        </p>

        <ol className="list-decimal pl-6 mb-6 text-stone-700 leading-relaxed space-y-2">
          <li>
            Trust that the vendor&rsquo;s disruption reports are the whole
            story.
          </li>
          <li>Sit in your own middle.</li>
        </ol>

        <p className="text-stone-700 leading-relaxed mb-6">
          Option one is what most enterprises are doing today. Option two is
          a proxy — vendor-agnostic, in front of every LLM call, logging
          every prompt, scoping every key to a real identity, catching the
          orchestration patterns <em>before</em> they leave your perimeter,
          and giving you a first-class inventory of the agents (sanctioned
          and shadow) that exist inside your walls.
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          Conduct is one such middle. There are others. The specific product
          matters less than the architectural choice.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          The takeaway
        </h2>

        <p className="text-stone-700 leading-relaxed mb-6">
          Anthropic&rsquo;s report is not a story about their models being
          unsafe. It is a story about what an adversary can do with a
          legitimate API key and a laptop. The organisations that come out of
          the next twelve months well will be the ones who read this report,
          looked at their own key inventory, and put the same kind of eyes on
          their own traffic that Anthropic put on theirs.
        </p>

        <p className="text-stone-700 leading-relaxed mb-6">
          The vendor is watching their side. Someone on your side needs to be
          watching yours.
        </p>
      </div>
    </article>
  )
}
