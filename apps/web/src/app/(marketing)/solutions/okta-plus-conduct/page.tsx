import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Okta + Conduct: complete AI agent governance | Conduct",
  description:
    "Okta issues the identity. Guard governs the action. Native sync of Okta agent identities into Conduct Guard, plus JWT authentication for runtime enforcement. Available now.",
}

export default function OktaPlusConductPage() {
  return (
    <>
      <HeroSection />
      <ProblemSection />
      <ThreeQuestionsSection />
      <LayerSplitSection />
      <IntegrationSection />
      <JwtAuthSection />
      <CtaSection />
    </>
  )
}

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        Reference architecture · Identity plus runtime governance
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        Okta issues the identity.{" "}
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">Guard governs the action.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-3xl mx-auto leading-relaxed mb-6">
        Okta AI Agent Import pulls every agent identity from Gemini Enterprise, DataRobot, Workday, Microsoft, Glean,
        and LangSmith into one directory. Guard sits at the wire and decides whether each of those identities is
        allowed to take the action it just requested. Same pattern as Okta plus a PAM tool for humans.
      </p>
      <p className="text-base text-stone-500 max-w-2xl mx-auto leading-relaxed italic mb-8">
        Your identity provider tells you who your agents are. Guard governs what they do.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a
          href="https://cal.com/sudhi-seshachala-pks7pd"
          target="_blank"
          rel="noopener"
          className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center"
        >
          Book a reference walkthrough
        </a>
        <a
          href="/use-cases#agent-identity"
          className="rounded-xl border border-stone-300 bg-white text-stone-700 px-7 py-3.5 text-base font-semibold hover:border-stone-400 hover:shadow-sm transition-all w-full sm:w-auto text-center"
        >
          Read the identity use case
        </a>
      </div>
    </section>
  )
}

const PROBLEMS = [
  {
    headline: "Every builder platform ships its own agent registry.",
    body: "Gemini Enterprise, DataRobot, Workday, Microsoft, Glean, LangSmith, Claude Managed Agents. Each maintains its own list of agents, its own owners, its own lifecycle. Your security team has to hunt across every platform to answer one question.",
  },
  {
    headline: "Identity is not enforcement.",
    body: "Okta answers who owns the agent and how to deactivate it. Neither Okta nor the source platform answers whether the agent should be allowed to issue that refund right now. Runtime governance is a separate layer.",
  },
  {
    headline: "Agents outpace governance without both layers.",
    body: "Gartner projects 40 percent of enterprise apps will run task-specific agents by end of 2026. Fewer than a third hold agents to human-identity standards. Filling that gap needs identity discovery and runtime enforcement, not one or the other.",
  },
]

function ProblemSection() {
  return (
    <section className="bg-stone-50 border-y border-stone-200 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-center text-2xl font-black text-stone-900 tracking-tight mb-10">
          Why identity alone is not enough.
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          {PROBLEMS.map((p) => (
            <div key={p.headline} className="border border-stone-200 rounded-xl bg-white p-6">
              <h3 className="text-sm font-bold text-stone-900 mb-2">{p.headline}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{p.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const QUESTIONS = [
  {
    n: "01",
    q: "Where are they?",
    owner: "Okta AI Agent Import",
    body: "Okta pulls agent identities from every supported builder platform into one directory. Owner, lifecycle, deactivation, access certifications. This is the discovery layer.",
  },
  {
    n: "02",
    q: "What can they connect to?",
    owner: "Okta plus Guard",
    body: "Okta handles the access model at the entitlement layer. Guard adds runtime scope: which credentials the agent may broker at run time, which resources fall inside the current session's permit.",
  },
  {
    n: "03",
    q: "What can they do?",
    owner: "Conduct Guard",
    body: "Guard evaluates every model call, MCP tool call, and action-tool call against policy. Allow, warn, or block returns before the action commits. Every decision lands in the hash-chained audit.",
  },
]

function ThreeQuestionsSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-20">
      <div className="text-center mb-12">
        <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight mb-4">
          Three questions, two layers.
        </h2>
        <p className="text-stone-500 max-w-2xl mx-auto">
          Okta's own security framing names three questions. Okta owns the first and helps with the second. The third
          is where Guard operates.
        </p>
      </div>
      <div className="space-y-4">
        {QUESTIONS.map((q) => (
          <div key={q.n} className="border border-stone-200 rounded-xl p-6 bg-white flex gap-5">
            <span className="text-xs font-mono text-stone-400 flex-shrink-0 mt-1">{q.n}</span>
            <div className="flex-1">
              <div className="flex items-baseline gap-3 mb-2">
                <h3 className="text-lg font-bold text-stone-900">{q.q}</h3>
                <span className="text-xs uppercase tracking-widest text-indigo-600 font-semibold">{q.owner}</span>
              </div>
              <p className="text-sm text-stone-600 leading-relaxed">{q.body}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

const LAYERS = [
  {
    role: "Okta AI Agent Import",
    covers: "Discovers agents across Gemini Enterprise, DataRobot, Workday, Microsoft, Glean, LangSmith, and Claude Managed Agents. Assigns owners. Runs access certifications. Handles deactivation and lifecycle. One identity registry across every builder platform.",
    where: "The identity layer.",
  },
  {
    role: "Conduct Guard",
    covers: "Consumes the identity registry as a source of Guard principals. Every Okta-imported agent becomes a first-class principal in Guard policy. Runtime decisions cite the Okta identity in the audit chain. Agents can authenticate to Guard with their Okta-issued JWTs, so Okta remains the single credential system.",
    where: "The runtime layer.",
  },
]

function LayerSplitSection() {
  return (
    <section className="bg-stone-50 border-y border-stone-200 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight mb-4">
            Two layers, one governance story.
          </h2>
          <p className="text-stone-500 max-w-2xl mx-auto">
            Okta issues. Conduct governs. The same layer split that Okta plus a privilege-access tool uses for humans,
            applied to the agent identity class.
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-5">
          {LAYERS.map((l) => (
            <div key={l.role} className="border border-stone-200 rounded-2xl p-6 bg-white">
              <p className="text-xs font-bold uppercase tracking-widest text-indigo-500 mb-2">{l.where}</p>
              <h3 className="text-lg font-bold text-stone-900 mb-3">{l.role}</h3>
              <p className="text-sm text-stone-600 leading-relaxed">{l.covers}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function IntegrationSection() {
  return (
    <section className="max-w-4xl mx-auto px-6 py-20">
      <h2 className="text-center text-3xl font-black text-stone-900 tracking-tight mb-6">
        Reference architecture.
      </h2>
      <p className="text-center text-stone-500 max-w-2xl mx-auto mb-10">
        How Okta AI Agent Import feeds Conduct Guard.
      </p>
      <div className="border border-stone-200 rounded-xl p-6 bg-stone-50 mb-6">
        <ol className="space-y-4 text-sm text-stone-700 leading-relaxed">
          <li>
            <span className="font-bold text-stone-900">1. Okta imports agents from builder platforms.</span>{" "}
            AI Agent Import pulls agent identities from Gemini, DataRobot, Workday, Microsoft, Glean, LangSmith, and
            Claude Managed Agents. Each agent gets a base profile with owner, source platform, and lifecycle state.
          </li>
          <li>
            <span className="font-bold text-stone-900">2. Guard pulls the identity registry from Okta.</span>{" "}
            An on-demand sync mirrors the Okta agent identity registry into Guard's agent-identity module. Owner is
            assigned on the first sync. Source platform and lifecycle state carry over on every sync. Scheduled sync
            is on the roadmap.
          </li>
          <li>
            <span className="font-bold text-stone-900">3. Guard principals reference Okta identity.</span>{" "}
            Every Guard policy rule can reference the Okta-imported identity as a principal. The audit chain records
            the Okta identity on every decision, giving auditors an accountable human on every row.
          </li>
          <li>
            <span className="font-bold text-stone-900">4. Lifecycle changes propagate.</span>{" "}
            Deactivating an agent in Okta marks it inactive on the next sync. The Okta status field is the source of
            truth for whether the identity is live. Runtime enforcement of Okta status is on the roadmap.
          </li>
          <li>
            <span className="font-bold text-stone-900">5. One control plane for humans and agents.</span>{" "}
            Access reviews in Okta cover both classes of identity. Runtime enforcement in Guard covers both classes of
            action. Compliance evidence attaches Okta identity to every Guard decision.
          </li>
        </ol>
      </div>
      <p className="text-xs text-stone-500 italic text-center">
        Available now. Configure at Agent Identity → Integrations.
      </p>
    </section>
  )
}

function JwtAuthSection() {
  return (
    <section className="bg-stone-50 border-y border-stone-200 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <p className="text-xs font-bold uppercase tracking-widest text-indigo-500 mb-3">Runtime authentication</p>
          <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight mb-4">
            Agents authenticate to Guard with their Okta identity.
          </h2>
          <p className="text-stone-500 max-w-2xl mx-auto leading-relaxed">
            No shared secrets between Okta and Conduct. Agents present an Okta-issued JWT. Guard verifies it against
            your Okta authorization server and treats the identity as a first-class Guard principal for policy
            evaluation.
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-5">
          <div className="border border-stone-200 rounded-2xl p-6 bg-white">
            <p className="text-xs font-bold uppercase tracking-widest text-indigo-500 mb-3">Setup</p>
            <ol className="text-sm text-stone-700 space-y-2 leading-relaxed">
              <li>1. Create an OAuth authorization server in Okta admin.</li>
              <li>2. Paste the issuer URL and audience into Agent Identity → Integrations.</li>
              <li>3. Toggle Enabled.</li>
            </ol>
          </div>
          <div className="border border-stone-200 rounded-2xl p-6 bg-white">
            <p className="text-xs font-bold uppercase tracking-widest text-indigo-500 mb-3">Runtime flow</p>
            <ol className="text-sm text-stone-700 space-y-2 leading-relaxed">
              <li>1. Agent requests a token from Okta.</li>
              <li>2. Agent calls Guard proxy with the Okta JWT as a Bearer token.</li>
              <li>3. Guard verifies the JWT against Okta JWKS, evaluates policy, and forwards to the LLM.</li>
            </ol>
          </div>
        </div>
      </div>
    </section>
  )
}

function CtaSection() {
  return (
    <section className="px-6 py-24 bg-gradient-to-br from-indigo-600 to-violet-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          One control plane for identity and action.
        </h2>
        <p className="text-indigo-100 text-lg mb-8">
          Okta issues the identity. Guard governs the action. Book a reference walkthrough or read the deep dive.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="https://cal.com/sudhi-seshachala-pks7pd"
            target="_blank"
            rel="noopener"
            className="rounded-xl bg-white text-indigo-600 px-8 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center"
          >
            Book a walkthrough
          </a>
          <a
            href="/use-cases#agent-identity"
            className="rounded-xl border border-white/40 text-white px-8 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center"
          >
            Read the identity use case
          </a>
        </div>
      </div>
    </section>
  )
}
