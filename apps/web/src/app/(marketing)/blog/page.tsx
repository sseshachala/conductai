export default function BlogIndex() {
  const posts = [
    {
      slug: "which-ai-model-for-which-task",
      title: "Which AI model should you use — and for which task?",
      excerpt: "Claude, GPT-4o, Gemini, DeepSeek, Mistral, Llama — a practical guide for developers on picking the right model for the job. With code examples and ConductGuard governance.",
      date: "June 5, 2026",
      tag: "Guide",
      tagColor: "text-amber-700 bg-amber-50 border-amber-200",
    },
    {
      slug: "stop-paying-opus-prices-for-haiku-work",
      title: "Stop paying Opus prices for Haiku work.",
      excerpt: "Most AI coding setups default to the most capable model for every task — including fixing a typo. That's a 4x cost penalty on work a cheaper model handles just as well.",
      date: "May 31, 2026",
      tag: "Agent Booster",
      tagColor: "text-amber-700 bg-amber-50 border-amber-200",
    },
    {
      slug: "rtk-how-we-cut-93-percent-of-cli-tokens",
      title: "RTK: how we cut 93% of CLI token noise from AI coding sessions.",
      excerpt: "Every time Claude runs a command, the full output lands in the context window. A single git log can burn 4,000 tokens. RTK filters that noise before it ever reaches the model.",
      date: "May 31, 2026",
      tag: "RTK",
      tagColor: "text-stone-700 bg-stone-100 border-stone-200",
    },
    {
      slug: "why-ai-reads-your-whole-file-when-it-only-needs-three-functions",
      title: "Why your AI reads the whole file when it only needs three functions.",
      excerpt: "AI coding tools aren't lazy — they're blind. They can't see inside a file without reading it. Agent Booster gives them a map so they don't have to.",
      date: "May 31, 2026",
      tag: "Agent Booster",
      tagColor: "text-indigo-700 bg-indigo-50 border-indigo-200",
    },
  ]

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <header className="px-6 py-5 flex items-center justify-between max-w-6xl mx-auto w-full">
        <a href="/">
          <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
        </a>
        <div className="flex items-center gap-4">
          <div className="relative group">
            <a href="/tools" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
              Tools
              <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
            </a>
            <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50">
              <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-1.5 min-w-[160px]">
                <a href="/tools/agent-booster" className="flex items-center gap-2 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
                  <span className="text-indigo-600 font-bold">◈</span> Agent Booster
                </a>
                <a href="/tools/conduct-cli" className="flex items-center gap-2 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
                  <span className="text-violet-600 font-bold">⬡</span> Conduct CLI
                </a>
              </div>
            </div>
          </div>
          <a href="/marketplace" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Agent Templates</a>
          <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-16 w-full">
        <h1 className="text-3xl font-bold text-stone-900 mb-2">Blog</h1>
        <p className="text-stone-500 mb-12">Thoughts on AI cost, context efficiency, and agentic development.</p>

        <div className="flex flex-col gap-8">
          {posts.map(post => (
            <a
              key={post.slug}
              href={`/blog/${post.slug}`}
              className="group block rounded-2xl border border-stone-200 px-7 py-6 hover:border-stone-300 hover:shadow-sm transition-all"
            >
              <div className="flex items-center gap-3 mb-3">
                <span className={`text-xs font-semibold border px-2.5 py-1 rounded-full uppercase tracking-widest ${post.tagColor}`}>
                  {post.tag}
                </span>
                <span className="text-xs text-stone-400">{post.date}</span>
              </div>
              <h2 className="text-lg font-bold text-stone-900 mb-2 group-hover:text-indigo-600 transition-colors">
                {post.title}
              </h2>
              <p className="text-sm text-stone-500 leading-relaxed">{post.excerpt}</p>
            </a>
          ))}
        </div>
      </main>
    </div>
  )
}
