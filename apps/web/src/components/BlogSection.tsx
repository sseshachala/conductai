"use client"

import { useEffect, useState } from "react"

interface FeedPost {
  id: string
  title: string
  url: string
  date_published: string
  summary: string
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

export default function BlogSection() {
  const [posts, setPosts] = useState<FeedPost[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("https://narratr.ai/blog/conductai/feed.json")
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data.posts)) setPosts(data.posts)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <section className="px-6 py-20 border-t border-stone-100">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">From the blog</p>
        <h2 className="text-2xl font-bold text-stone-900 text-center mb-10">Thinking out loud on AI + engineering</h2>

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {[1, 2, 3].map(i => (
              <div key={i} className="bg-white rounded-2xl border border-stone-200 p-6 flex flex-col gap-3 animate-pulse">
                <div className="h-3 bg-stone-100 rounded w-1/3" />
                <div className="h-4 bg-stone-100 rounded w-full" />
                <div className="h-4 bg-stone-100 rounded w-4/5" />
                <div className="h-3 bg-stone-100 rounded w-full mt-2" />
                <div className="h-3 bg-stone-100 rounded w-2/3" />
              </div>
            ))}
          </div>
        ) : posts.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {posts.map(post => (
              <a
                key={post.id}
                href={post.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group bg-white rounded-2xl border border-stone-200 p-6 flex flex-col gap-3 hover:border-stone-300 hover:shadow-sm transition-all"
              >
                <span className="text-[11px] text-stone-400">{formatDate(post.date_published)}</span>
                <p className="font-semibold text-stone-900 text-sm leading-snug group-hover:text-indigo-600 transition-colors">{post.title}</p>
                <p className="text-xs text-stone-500 leading-relaxed flex-1">{post.summary}</p>
                <span className="text-xs font-medium text-indigo-600 group-hover:underline mt-auto">Read on Narratr →</span>
              </a>
            ))}
          </div>
        ) : null}

        <div className="text-center mt-8">
          <a
            href="https://narratr.ai/blog/conductai"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-medium text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
          >
            View all posts →
          </a>
        </div>
      </div>
    </section>
  )
}
