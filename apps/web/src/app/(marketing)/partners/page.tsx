"use client"

export default function PartnersPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main className="flex-1">
        <HeroSection />
        <PartnerTypesSection />
        <WhyPartnerSection />
        <WhatYouGetSection />
        <ApplySection />
      </main>
      <PageFooter />
    </div>
  )
}

/* ─── Nav ──────────────────────────────────────────────────────────────── */

function Nav() {
  return (
    <header className="px-6 py-4 flex items-center justify-between max-w-6xl mx-auto w-full sticky top-0 bg-white/95 backdrop-blur-sm z-50 border-b border-stone-100">
      <a href="/"><img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" /></a>
      <nav className="hidden md:flex items-center gap-6">
        <ProductsDropdown />
        <a href="/playbooks" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Playbooks</a>
        <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
        <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
        <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">GitHub</a>
      </nav>
      <div className="flex items-center gap-3">
        <a href="mailto:hello@conductai.ai" className="text-sm font-medium text-stone-600 hover:text-stone-900 transition-colors hidden sm:block">Talk to Us</a>
        <a href="/sign-up" className="rounded-lg bg-stone-900 text-white px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors">Start Free</a>
      </div>
    </header>
  )
}

function ProductsDropdown() {
  return (
    <div className="relative group">
      <a href="/sign-up" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Products
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[220px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/guard-landing" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🛡️</span>
            <div>
              <p className="font-semibold">Conduct Guard</p>
              <p className="text-xs text-stone-400">AI session governance</p>
            </div>
          </a>
          <a href="/tools/security-loop" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🔒</span>
            <div>
              <p className="font-semibold">Security Loop</p>
              <p className="text-xs text-stone-400">Automated PR scanning</p>
            </div>
          </a>
          <a href="/playbooks" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>⚡</span>
            <div>
              <p className="font-semibold">Playbooks</p>
              <p className="text-xs text-stone-400">Pre-built AI automations</p>
            </div>
          </a>
          <a href="/tools/conduct-cli" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-indigo-600 font-bold text-base">◈</span>
            <div>
              <p className="font-semibold">Conduct CLI</p>
              <p className="text-xs text-stone-400">Terminal governance + token savings</p>
            </div>
          </a>
        </div>
      </div>
    </div>
  )
}


function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-4">Partners</p>
      <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-tight mb-6">
        Build with us.<br />
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">Not just on us.</span>
      </h1>
      <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed mb-8">
        AI governance is not a product category you install and forget. It's a practice that takes
        people, process, and technology working together. We're looking for partners who want to
        build that practice alongside us — in any form that makes sense.
      </p>
      <a href="#apply" className="inline-flex rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-bold hover:bg-stone-700 transition-colors">
        Tell Us How You'd Like to Partner →
      </a>
    </section>
  )
}

/* ─── Partner Types ────────────────────────────────────────────────────── */

const partnerTypes = [
  {
    icon: "🏢",
    iconBg: "bg-indigo-50",
    label: "Solutions Partners",
    title: "Implement governance for your clients.",
    desc: "You're a consulting firm, systems integrator, or managed services provider. Your clients are adopting AI and need someone to own the governance layer for them. You bring the relationship — we bring the platform and the playbooks.",
    outcomes: [
      "White-label or co-branded delivery",
      "Access to full platform + implementation tooling",
      "Joint sales support and proposal templates",
      "Training and certification for your team",
      "Revenue share on platform subscriptions",
    ],
    cta: "Become a Solutions Partner",
  },
  {
    icon: "🔧",
    iconBg: "bg-emerald-50",
    label: "Technology Partners",
    title: "Integrate Conduct into your platform.",
    desc: "You build developer tools, security platforms, or engineering infrastructure. Your users are already using AI. Adding Conduct's governance layer — Guard policies, audit trails, spend controls — makes your platform more defensible.",
    outcomes: [
      "MCP integration support",
      "API access for audit log and policy data",
      "Co-marketing and joint case studies",
      "Early access to new features",
      "Listed in Conduct's integration directory",
    ],
    cta: "Explore a Technical Integration",
  },
  {
    icon: "📖",
    iconBg: "bg-amber-50",
    label: "Referral Partners",
    title: "Connect us to teams that need governance.",
    desc: "You work with engineering organizations, CISOs, or IT leaders. When AI governance comes up in conversation — and it will — you refer them to Conduct. Simple, low-touch, valuable.",
    outcomes: [
      "Referral fee on closed platform subscriptions",
      "Solutions engagements for referred clients",
      "Partner portal with deal tracking",
      "No quota, no exclusivity required",
      "Conduct team handles everything after intro",
    ],
    cta: "Become a Referral Partner",
  },
  {
    icon: "🎓",
    iconBg: "bg-violet-50",
    label: "Community & Research Partners",
    title: "Advance the practice of AI governance.",
    desc: "You're a researcher, educator, community builder, or open-source contributor working on responsible AI, developer tooling, or engineering culture. We want to collaborate — not just commercially, but intellectually.",
    outcomes: [
      "Access to Conduct's data and findings",
      "Platform access for research and teaching",
      "Speaking and writing collaboration",
      "Open-source contributions welcomed",
      "No commercial requirement",
    ],
    cta: "Start a Conversation",
  },
]

function PartnerTypesSection() {
  return (
    <section className="py-20 px-6 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">Partnership Tracks</p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight mb-4">
            Every kind of partnership.<br />One application.
          </h2>
          <p className="text-stone-500 max-w-xl mx-auto leading-relaxed">
            We're open to any collaboration that helps engineering teams govern their AI.
            Tell us what you're thinking — we'll figure out the right fit together.
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-5">
          {partnerTypes.map(p => (
            <div key={p.label} className="bg-white rounded-2xl border border-stone-200 p-7 flex flex-col gap-4 hover:border-stone-300 hover:shadow-sm transition-all">
              <div className="flex items-center gap-3">
                <div className={`w-11 h-11 rounded-xl ${p.iconBg} flex items-center justify-center text-xl`}>
                  {p.icon}
                </div>
                <p className="text-xs font-bold uppercase tracking-widest text-stone-400">{p.label}</p>
              </div>
              <div>
                <h3 className="text-xl font-bold text-stone-900 tracking-tight mb-2">{p.title}</h3>
                <p className="text-sm text-stone-500 leading-relaxed">{p.desc}</p>
              </div>
              <ul className="space-y-2">
                {p.outcomes.map(o => (
                  <li key={o} className="flex items-start gap-2 text-sm text-stone-600">
                    <span className="text-indigo-500 font-bold flex-shrink-0">→</span>
                    {o}
                  </li>
                ))}
              </ul>
              <a href="#apply" className="mt-auto text-sm font-semibold text-indigo-600 hover:text-indigo-800 transition-colors">
                {p.cta} →
              </a>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Why Partner ──────────────────────────────────────────────────────── */

function WhyPartnerSection() {
  const reasons = [
    {
      title: "AI governance is a growing requirement — not a nice-to-have.",
      body: "SOC 2, ISO 27001, and emerging AI-specific compliance frameworks are all asking the same question: how do you govern what your AI tools do? The teams that can answer that question are the ones that win enterprise deals. We help you answer it.",
    },
    {
      title: "SaaS alone isn't a moat anymore. Expertise is.",
      body: "Anyone can build software now. What can't be replicated is the knowledge of how to apply AI governance in a real engineering organization — the policy design, the organizational change, the integration with existing security practice. Partners who carry that expertise have a durable advantage.",
    },
    {
      title: "We built the platform. You bring the relationships.",
      body: "Conduct is the technical layer: Guard, Secure, Agentic Workflows, the audit trail, the policy library. You bring the client relationship, the implementation capacity, or the distribution. Together we can move faster than either of us alone.",
    },
  ]
  return (
    <section className="py-20 px-6 bg-white">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">Why Partner With Conduct</p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight">
            The case for building<br />this together.
          </h2>
        </div>
        <div className="grid md:grid-cols-3 gap-5">
          {reasons.map(r => (
            <div key={r.title} className="rounded-2xl border border-stone-200 p-6">
              <h3 className="text-base font-bold text-stone-900 mb-3 leading-snug">{r.title}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{r.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── What You Get ─────────────────────────────────────────────────────── */

function WhatYouGetSection() {
  const items = [
    { icon: "🚀", title: "Full platform access", desc: "Every feature — Guard, Secure, Workflows, the marketplace, and the canvas — available to you and your team for delivery and demo." },
    { icon: "📚", title: "Implementation playbooks", desc: "The same runbooks we use internally to deploy governance across engineering teams. Adapted for partner delivery." },
    { icon: "🤝", title: "Joint go-to-market", desc: "Co-marketing, case studies, speaking opportunities, and introductions to our network. We build pipeline together." },
    { icon: "🛠️", title: "Technical support", desc: "Direct line to the Conduct engineering team. For technical questions, custom integrations, and edge cases in client deployments." },
    { icon: "📊", title: "Partner portal", desc: "Deal registration, revenue tracking, training materials, and certification — all in one place." },
    { icon: "💬", title: "Shared Slack channel", desc: "Real-time communication with the Conduct team. Not a ticket queue — a conversation." },
  ]
  return (
    <section className="py-20 px-6 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">What Partners Get</p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight mb-4">
            We invest in partners<br />who invest in clients.
          </h2>
          <p className="text-stone-500 max-w-xl mx-auto leading-relaxed">
            We don't have a partner program with a PDF and a badge.
            We have actual support — people, tools, and shared upside.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {items.map(item => (
            <div key={item.title} className="bg-white rounded-2xl border border-stone-200 p-5 hover:border-stone-300 hover:shadow-sm transition-all">
              <div className="text-2xl mb-3">{item.icon}</div>
              <h3 className="text-sm font-bold text-stone-900 mb-2">{item.title}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Apply ────────────────────────────────────────────────────────────── */

function ApplySection() {
  return (
    <section id="apply" className="py-24 px-6 bg-stone-900">
      <div className="max-w-2xl mx-auto text-center">
        <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-4">Get Started</p>
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          Tell us how you'd<br />like to work together.
        </h2>
        <p className="text-stone-400 leading-relaxed mb-10">
          No form with 40 fields. No sales qualification call before we've even talked.
          Send us a note — tell us who you are, what you're building, and what kind of
          partnership you have in mind. We'll respond within one business day.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="mailto:hello@conductai.ai"
            className="rounded-xl bg-white text-stone-900 px-7 py-3.5 text-base font-bold hover:bg-stone-100 transition-colors w-full sm:w-auto text-center"
          >
            Email Us — hello@conductai.ai
          </a>
          <a
            href="mailto:hello@conductai.ai"
            className="rounded-xl border border-white/20 text-white px-7 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center"
          >
            Book a 30-Minute Call
          </a>
        </div>
        <p className="text-stone-500 text-xs mt-6">
          Already a customer exploring a deeper relationship? Same links. We'll figure out the right structure together.
        </p>
      </div>
    </section>
  )
}

/* ─── Footer ───────────────────────────────────────────────────────────── */

function PageFooter() {
  return (
    <footer className="border-t border-stone-100 py-8 px-6 bg-white">
      <div className="max-w-5xl mx-auto flex flex-col sm:flex-row justify-between items-center gap-4 text-xs text-stone-400">
        <div className="flex items-center gap-4 flex-wrap justify-center">
          <span>© {new Date().getFullYear()} Conduct AI</span>
          <a href="/" className="hover:text-stone-600 transition-colors">Home</a>
          <a href="/solutions" className="hover:text-stone-600 transition-colors">Solutions</a>
          <a href="/docs" className="hover:text-stone-600 transition-colors">Docs</a>
          <a href="/privacy" className="hover:text-stone-600 transition-colors">Privacy</a>
          <a href="/terms" className="hover:text-stone-600 transition-colors">Terms</a>
        </div>
        <span className="text-stone-300">Envisioned, designed and developed with love from Houston</span>
      </div>
    </footer>
  )
}
