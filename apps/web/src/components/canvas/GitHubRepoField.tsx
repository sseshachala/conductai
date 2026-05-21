"use client"

import { useEffect, useRef, useState } from "react"

const API = process.env.NEXT_PUBLIC_API_URL

interface Repo {
  full_name: string
  owner: string
  name: string
}

// Shared in-memory cache so multiple fields don't re-fetch within a session.
let reposCache: Repo[] | null = null
const branchCache: Record<string, string[]> = {}

function getWorkspaceHeader(): Record<string, string> {
  if (typeof document === "undefined") return {}
  const match = document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)
  return match ? { "X-Workspace-Id": match[1] } : {}
}

// ── Repo picker ───────────────────────────────────────────────────────────────

interface RepoFieldProps {
  value: string
  onChange: (owner: string, repo: string) => void
  getToken?: (() => Promise<string | null>) | null
}

export function GitHubRepoField({ value, onChange, getToken }: RepoFieldProps) {
  const [repos, setRepos] = useState<Repo[]>(reposCache ?? [])
  const [loading, setLoading] = useState(!reposCache)
  const [search, setSearch] = useState(value || "")
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (reposCache) { setRepos(reposCache); setLoading(false); return }
    ;(async () => {
      try {
        const headers: Record<string, string> = { ...getWorkspaceHeader() }
        if (getToken) {
          const token = await getToken()
          if (token) headers["Authorization"] = `Bearer ${token}`
        }
        const r = await fetch(`${API}/credentials/github/repos`, { headers })
        if (r.ok) {
          const data: Repo[] = await r.json()
          reposCache = data
          setRepos(data)
        }
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  const filtered = repos.filter(r => r.full_name.toLowerCase().includes(search.toLowerCase())).slice(0, 30)

  function select(repo: Repo) {
    setSearch(repo.full_name)
    setOpen(false)
    onChange(repo.owner, repo.name)
  }

  const base = "w-full border border-stone-200 rounded-lg px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white"

  return (
    <div className="relative" ref={ref}>
      <input
        type="text"
        value={search}
        onChange={e => { setSearch(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        placeholder={loading ? "Loading repos…" : "owner/repo"}
        className={base}
      />
      {open && (
        <div className="absolute z-30 mt-1 w-full bg-white border border-stone-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
          {loading ? (
            <p className="px-3 py-2 text-xs text-stone-400">Loading…</p>
          ) : filtered.length === 0 ? (
            <p className="px-3 py-2 text-xs text-stone-400">No repos found</p>
          ) : filtered.map(r => (
            <button
              key={r.full_name}
              onMouseDown={() => select(r)}
              className="w-full text-left px-3 py-2 text-xs text-stone-700 hover:bg-stone-50 truncate"
            >
              {r.full_name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Repo allowlist picker (multi, comma-separated) ───────────────────────────

interface RepoAllowlistFieldProps {
  value: string   // comma-separated "owner/repo" values
  onChange: (value: string) => void
  getToken?: (() => Promise<string | null>) | null
}

export function GitHubRepoAllowlistField({ value, onChange, getToken }: RepoAllowlistFieldProps) {
  const [repos, setRepos] = useState<Repo[]>(reposCache ?? [])
  const [loading, setLoading] = useState(!reposCache)
  const [search, setSearch] = useState("")
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const selected = value ? value.split(",").map(s => s.trim()).filter(Boolean) : []

  useEffect(() => {
    if (reposCache) { setRepos(reposCache); setLoading(false); return }
    ;(async () => {
      try {
        const headers: Record<string, string> = { ...getWorkspaceHeader() }
        if (getToken) {
          const token = await getToken()
          if (token) headers["Authorization"] = `Bearer ${token}`
        }
        const r = await fetch(`${API}/credentials/github/repos`, { headers })
        if (r.ok) {
          const data: Repo[] = await r.json()
          reposCache = data
          setRepos(data)
        }
      } finally { setLoading(false) }
    })()
  }, [])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  const filtered = repos
    .filter(r => !selected.includes(r.full_name))
    .filter(r => r.full_name.toLowerCase().includes(search.toLowerCase()))
    .slice(0, 20)

  function add(fullName: string) {
    const next = [...selected, fullName].join(", ")
    onChange(next)
    setSearch("")
    setOpen(false)
  }

  function remove(fullName: string) {
    onChange(selected.filter(s => s !== fullName).join(", "))
  }

  return (
    <div className="space-y-1.5" ref={ref}>
      {/* Selected chips */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.map(repo => (
            <span key={repo} className="inline-flex items-center gap-1 bg-stone-100 text-stone-700 text-xs px-2 py-0.5 rounded-full">
              {repo}
              <button
                type="button"
                onMouseDown={() => remove(repo)}
                className="text-stone-400 hover:text-stone-700 leading-none"
              >×</button>
            </span>
          ))}
        </div>
      )}

      {/* Typeahead input */}
      <div className="relative">
        <input
          type="text"
          value={search}
          onChange={e => { setSearch(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          placeholder={loading ? "Loading repos…" : "Add repo…"}
          className="w-full border border-stone-200 rounded-lg px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white"
        />
        {open && (search || repos.length > 0) && (
          <div className="absolute z-30 mt-1 w-full bg-white border border-stone-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
            {loading ? (
              <p className="px-3 py-2 text-xs text-stone-400">Loading…</p>
            ) : filtered.length === 0 ? (
              <p className="px-3 py-2 text-xs text-stone-400">{search ? "No matching repos" : "All repos added"}</p>
            ) : filtered.map(r => (
              <button
                key={r.full_name}
                type="button"
                onMouseDown={() => add(r.full_name)}
                className="w-full text-left px-3 py-2 text-xs text-stone-700 hover:bg-stone-50 truncate"
              >
                {r.full_name}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Branch picker ─────────────────────────────────────────────────────────────

interface BranchFieldProps {
  owner: string
  repo: string
  value: string
  onChange: (branch: string) => void
  getToken?: (() => Promise<string | null>) | null
}

export function GitHubBranchField({ owner, repo, value, onChange, getToken }: BranchFieldProps) {
  const [branches, setBranches] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState(value || "")
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!owner || !repo) return
    const key = `${owner}/${repo}`
    if (branchCache[key]) { setBranches(branchCache[key]); return }
    setLoading(true)
    ;(async () => {
      try {
        const headers: Record<string, string> = { ...getWorkspaceHeader() }
        if (getToken) {
          const token = await getToken()
          if (token) headers["Authorization"] = `Bearer ${token}`
        }
        const r = await fetch(`${API}/credentials/github/repos/${owner}/${repo}/branches`, { headers })
        if (r.ok) {
          const data: { name: string }[] = await r.json()
          const names = data.map(b => b.name)
          branchCache[key] = names
          setBranches(names)
        }
      } finally {
        setLoading(false)
      }
    })()
  }, [owner, repo])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  const filtered = branches.filter(b => b.toLowerCase().includes(search.toLowerCase()))

  const base = "w-full border border-stone-200 rounded-lg px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white"

  if (!owner || !repo) {
    return <input type="text" value={search} onChange={e => { setSearch(e.target.value); onChange(e.target.value) }} placeholder="Select a repo first" className={base} disabled />
  }

  return (
    <div className="relative" ref={ref}>
      <input
        type="text"
        value={search}
        onChange={e => { setSearch(e.target.value); setOpen(true); onChange(e.target.value) }}
        onFocus={() => setOpen(true)}
        placeholder={loading ? "Loading branches…" : "branch name"}
        className={base}
      />
      {open && (
        <div className="absolute z-30 mt-1 w-full bg-white border border-stone-200 rounded-lg shadow-lg max-h-40 overflow-y-auto">
          {loading ? (
            <p className="px-3 py-2 text-xs text-stone-400">Loading…</p>
          ) : filtered.length === 0 ? (
            <p className="px-3 py-2 text-xs text-stone-400">No branches found</p>
          ) : filtered.map(b => (
            <button
              key={b}
              onMouseDown={() => { setSearch(b); setOpen(false); onChange(b) }}
              className="w-full text-left px-3 py-2 text-xs text-stone-700 hover:bg-stone-50"
            >
              {b}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
