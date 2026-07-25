import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Fix this code: three words that changed AI security. | Conduct",
  description:
    "On June 12, 2026 the US government shut down Anthropic's Fable 5 and Mythos 5 over a three-word prompt. The lesson isn't about the model. It's about who's watching what the AI is allowed to do.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-red-700 bg-red-50 border border-red-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Security
          </span>
          <span className="text-xs text-stone-400">July 25, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          Fix this code: three words that changed AI security.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          On June 12, the US government shut down two of the most capable AI models on the planet.
          The trigger wasn&apos;t a jailbreak, a data leak, or a nation-state attack. It was a three-word
          prompt any developer types twenty times a day.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What happened</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          On June 9, Anthropic released two new models. Claude Fable 5 for the general public, and
          Claude Mythos 5 for approved cybersecurity partners. Same underlying model. Different
          safeguards. Fable had cybersecurity topics blocked and would fall back to Opus 4.8.
          Mythos had those blocks lifted for a small circle of partners.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          Three days later, at 5:21 PM ET on June 12, Anthropic received a US government
          export-control directive citing national security. Within hours, both models were
          disabled for every customer worldwide.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          The exploit that triggered it was three words.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The fix this code vector</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Researchers asked Fable 5 to <em>review this code for security issues</em>. The safeguard
          worked. The model refused.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          Then they asked <em>fix this code</em>. The model happily produced patches.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          To generate a patch, the model has to find the vulnerability first. Same capability, different
          framing. The safeguard was watching for one intent and let the other one through. That&apos;s not
          a bug. It&apos;s a category error. Refusing a phrasing does not refuse a capability.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Why safer models don&apos;t solve this</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          The next model will be more capable, not less. The next safeguard will be tighter, and
          someone will find the next three-word prompt. This is the pattern, not the exception.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          The permission set an agent has, once it&apos;s running, becomes your attack surface. Ashish
          Rajan made this point about the OpenAI / Hugging Face incident, and the Fable / Mythos
          shutdown is the same story in a smaller frame. The model wasn&apos;t trying to hack anything.
          It was completing a task. The surrounding permissions decided what completion looked like.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What Conduct ships about this today</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Conduct Guard sits on the wire in front of every LLM call. Two rules went out today in
          the conduct-base pack v2.8.0. Anyone with the pack installed picks them up on the next
          policy refresh. No engine changes. No new module.
        </p>

        <div className="bg-stone-50 border border-stone-200 rounded-xl p-6 mb-6">
          <p className="text-sm font-semibold text-stone-900 mb-2">
            proxy-fix-this-code-intent <span className="text-xs font-normal text-stone-500">— warn</span>
          </p>
          <p className="text-sm text-stone-600 leading-relaxed">
            Matches the <em>fix / patch / refactor this code</em> family of prompts. Warns the developer
            and logs the event to the hash-chained audit trail. Admin can raise to <em>block</em> per
            workspace. The intent is legible; the exception is documented.
          </p>
        </div>

        <div className="bg-stone-50 border border-stone-200 rounded-xl p-6 mb-6">
          <p className="text-sm font-semibold text-stone-900 mb-2">
            proxy-restricted-model-mythos-fable <span className="text-xs font-normal text-stone-500">— warn</span>
          </p>
          <p className="text-sm text-stone-600 leading-relaxed">
            Matches on the <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">model</code> field
            of the LLM call. Warns when a Mythos or Fable-class model is invoked. Admin can raise to
            <em> block </em>or route to approval based on repo tag. The CISO gets a legible answer to
            <em> which models are running on which code.</em>
          </p>
        </div>

        <p className="text-stone-700 leading-relaxed mb-6">
          Both rules ship tagged <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">security_policy</code>
          and surface in the new Security tab on <code className="text-xs bg-stone-100 px-1 py-0.5 rounded">/theguard/policies</code>.
          The rule engine already supported matching on model and prompt fields. This is a data change,
          not a code change.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The bigger takeaway</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Model-choice governance and intent-detection are becoming first-class controls, on the same
          shelf as identity and access. Not because the models are getting worse. Because the models
          are getting better, and the same capability that fixes your code can find the vulnerabilities
          in it.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          The question a CISO can ask their board next quarter is no longer <em>can AI hack?</em>
          It&apos;s <em>which models are running on our code, what are they being asked to do, and
          who&apos;s watching?</em>
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          Guard&apos;s answer to that question is short. On the wire. Every call. Every decision. Fail
          closed. Hash chained. If you want to see it in a demo, the calendar is open.
        </p>

        <div className="mt-12 border-t border-stone-100 pt-8">
          <CtaLink className="rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors" />
        </div>

      </div>
    </article>
  )
}
