import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Fix this code: the framing gap behind an 18-day model shutdown | Conduct",
  description:
    "Fable 5 returned after an 18-day shutdown. The lasting lesson is how ordinary coding prompts can cross a safeguard boundary—and why enterprises need model and intent governance.",
}

const sourceLink =
  "font-medium text-stone-700 underline decoration-stone-300 underline-offset-4 hover:text-indigo-600"

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-red-700 bg-red-50 border border-red-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Security
          </span>
          <span className="text-xs text-stone-400">July 25, 2026 · Updated August 7, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          Fix this code: the framing gap behind an 18-day model shutdown.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          On June 12, the US government ordered two of the most capable AI models on the
          planet taken offline. Eighteen days later, the order was lifted. The interesting
          part is not the outage. It is what the reported trigger says about how safeguards
          fail—and that part did not get reversed on June 30.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">
        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What happened</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          On June 9, Anthropic released{" "}
          <a
            className={sourceLink}
            href="https://www.anthropic.com/news/claude-fable-5-mythos-5"
            target="_blank"
            rel="noreferrer"
          >
            Claude Fable 5 and Claude Mythos 5
          </a>
          . Fable was available to the public; Mythos was restricted to trusted Project
          Glasswing partners working in defensive cybersecurity. Fable ran classifiers over
          cybersecurity, biology and chemistry, and distillation requests. At launch, flagged
          requests fell back to Opus 4.8.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          Three days later, at 5:21 PM ET on June 12, Anthropic received a US government
          export-control directive citing national security. The order barred access by foreign
          nationals anywhere. With no way to verify nationality in real time, Anthropic disabled
          both models globally.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          The{" "}
          <a
            className={sourceLink}
            href="https://www.anthropic.com/news/fable-mythos-access"
            target="_blank"
            rel="noreferrer"
          >
            directive gave no specific details
          </a>
          . Anthropic said its understanding was that the government believed it had learned of
          a way to bypass, or jailbreak, Fable 5. Anthropic described the evidence it received as
          a narrow, non-universal technique that essentially asked the model to read a codebase
          and fix its software flaws.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          The controls were{" "}
          <a
            className={sourceLink}
            href="https://www.anthropic.com/news/redeploying-fable-5"
            target="_blank"
            rel="noreferrer"
          >
            lifted on June 30
          </a>
          . Fable returned globally on July 1, and Mythos was restored to a set of US
          organizations following government approval on June 26. The shutdown ended. The
          framing problem did not.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The framing gap</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Whatever did or did not reach the government&apos;s desk, the reported technique is
          worth sitting with because it is not exotic.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          Ask a guarded model to <em>review this code for security issues</em> and the classifier
          gets a clean signal: the security intent is explicit. Ask it to <em>fix this code</em>
          and the request looks like one of the most ordinary things a developer types all day.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          But producing a useful patch still requires the model to locate the flaw. Same
          capability, different framing. That is the category error:{" "}
          <strong>refusing a phrasing does not refuse a capability.</strong>
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          This is an interpretation of the reported mechanism, not a published transcript of the
          government&apos;s test. Anthropic disputes the idea that the technique amounted to a
          universal bypass. Whether the decisive prompt was literally three words matters less
          than the overlap between the apparently safe task and the restricted capability.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          Why safer models do not close this
        </h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          The next model will be more capable, not less. The next safeguard will be tighter, and
          someone will find another framing that crosses its boundary. Pattern, not exception.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          The permission set an agent holds once it is running is the practical attack surface.
          Ashish Rajan&apos;s{" "}
          <a
            className={sourceLink}
            href="https://www.cloudsecuritynewsletter.com/p/openai-ai-hugging-face-attack"
            target="_blank"
            rel="noreferrer"
          >
            coverage of the OpenAI and Hugging Face incident
          </a>{" "}
          is an adjacent example: an agent&apos;s surrounding access determines the blast radius
          of task completion. Model safeguards matter, but permissions decide what completion can
          touch.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">
          What Conduct ships about this
        </h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          For LLM traffic intentionally routed through the Conduct Guard proxy, policy can inspect
          the requested model and prompt before the call reaches the provider. Two rules ship in
          the conduct-base pack v2.8.0. Installed workspaces receive them on policy refresh. No
          engine change or new module was required; the controls are versioned policy data.
        </p>

        <div className="bg-stone-50 border border-stone-200 rounded-xl p-6 mb-6">
          <p className="text-sm font-semibold text-stone-900 mb-2">
            proxy-fix-this-code-intent{" "}
            <span className="text-xs font-normal text-stone-500">— warn</span>
          </p>
          <p className="text-sm text-stone-600 leading-relaxed">
            Matches the <em>fix / patch / repair / refactor this code</em> family of prompts. It
            warns the caller and records the policy decision. A workspace admin can strengthen the
            action to <em>block</em>. The intent becomes visible, and any exception becomes an
            explicit policy choice.
          </p>
        </div>

        <div className="bg-stone-50 border border-stone-200 rounded-xl p-6 mb-6">
          <p className="text-sm font-semibold text-stone-900 mb-2">
            proxy-restricted-model-mythos-fable{" "}
            <span className="text-xs font-normal text-stone-500">— warn</span>
          </p>
          <p className="text-sm text-stone-600 leading-relaxed">
            Matches Mythos- or Fable-class names in the{" "}
            <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">model</code> field. It warns
            when one is requested; a workspace admin can strengthen the rule to <em>block</em>.
            The resulting audit event helps answer which governed model requests were made and
            under which workspace policy.
          </p>
        </div>

        <p className="text-stone-700 leading-relaxed mb-4">
          Both rules are tagged{" "}
          <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">security_policy</code> and
          appear in the Security view under{" "}
          <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">
            /theguard/policies
          </code>
          . Both default to <em>warn</em> deliberately. A control that blocks a developer&apos;s
          most common request on day one is likely to be disabled on day two. Teams can observe
          their own traffic, then tighten policy with evidence.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          These are proxy rules, not universal controls. They apply when traffic reaches the Guard
          proxy. Direct provider calls and local tool actions outside that governed surface are
          not covered by these two rules.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The takeaway</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Model-choice governance and intent detection are becoming first-class controls, on the
          same shelf as identity and access. Not because models are getting worse, but because
          they are getting better—and the same capability that fixes code can first find what is
          wrong with it.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          The board-level question is no longer only <em>can AI find vulnerabilities?</em> It is{" "}
          <em>
            which models are running against our code, what are they being asked to do, and which
            control points can see or stop those requests?
          </em>
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          For routed calls, Guard makes that decision visible before the provider request and
          records the result in the audit trail. Whether the policy warns or blocks is the
          workspace&apos;s choice.
        </p>

        <div className="mt-12 border-t border-stone-100 pt-8">
          <CtaLink className="rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors" />
        </div>
      </div>
    </article>
  )
}
