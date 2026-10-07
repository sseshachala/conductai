"use client"

import { authEnabled, apiUrl } from "@/lib/auth/runtime"


import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useAuth } from "@/lib/auth/client"
import { useWorkspace } from "@/lib/WorkspaceContext"
import AppShell from "@/components/AppShell"
import ModulesManager from "@/components/settings/ModulesManager"
import {
  CATEGORY_LABELS, CATEGORY_ORDER, FRIENDLY_NAMES, GITHUB_WEBHOOK_SLUGS, PACK_CATALOG,
  type Environment, type Playbook, type PlaybookInput, type PlaybookScore, type Project, type Repo,
} from "./_components/catalog"
import { MCPConnectPanel, ProxyConnectPanel } from "./_components/ConnectPanels"
import { SkillPacksTab } from "./_components/SkillPacksTab"
import { TemplatesTab } from "./_components/TemplatesTab"
import { YamlModal } from "./_components/YamlModal"
import { InstallModal } from "./_components/InstallModal"

export default function RegistryPage() {
  const clerkEnabled = authEnabled()
  if (clerkEnabled) return <RegistryWithAuth />
  return <RegistryContent getToken={null} />
}

function RegistryWithAuth() {
  const { getToken } = useAuth()
  return <RegistryContent getToken={getToken} />
}

function RegistryContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const { activeWorkspace } = useWorkspace()
  const router = useRouter()
  const searchParams = useSearchParams()
  const [marketTab, setMarketTab] = useState<"templates" | "modules" | "compliance" | "mcp" | "proxy">(
    searchParams?.get("tab") === "compliance" ? "compliance" : searchParams?.get("tab") === "modules" ? "modules" : searchParams?.get("tab") === "mcp" ? "mcp" : searchParams?.get("tab") === "proxy" ? "proxy" : "templates"
  )
  const [installedPacks, setInstalledPacks] = useState<Set<string>>(new Set())
  const [packInstalling, setPackInstalling] = useState<string | null>(null)
  // Pack catalog is fetched from the server so adding a new pack file is a
  // single-place change. Falls back to the hardcoded PACK_CATALOG on error.
  const [packCatalog, setPackCatalog] = useState<typeof PACK_CATALOG>(PACK_CATALOG)
  const [playbooks, setPlaybooks] = useState<Playbook[]>([])
  const [loading, setLoading] = useState(true)
  const [activeCategory, setActiveCategory] = useState("All")
  const [search, setSearch] = useState("")
  const [installing, setInstalling] = useState(false)
  const [installedCount, setInstalledCount] = useState<Map<string, number>>(new Map())
  const [installedWorkflowId, setInstalledWorkflowId] = useState<Map<string, string>>(new Map())
  const [uninstalling, setUninstalling] = useState<string | null>(null)
  const [scores, setScores] = useState<Map<string, PlaybookScore>>(new Map())
  useEffect(() => {
    const wsId = activeWorkspace?.id ?? null
    if (!wsId) return
    authHeaders().then(h =>
      fetch(`${apiUrl()}/compliance/packs/installed?workspace_id=${wsId}`, { headers: h })
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (d?.installed) setInstalledPacks(new Set(d.installed)) })
        .catch(() => {})
    )
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Load pack catalog once from the server. Falls back to the hardcoded
  // PACK_CATALOG (already the initial state) if the fetch fails.
  useEffect(() => {
    fetch(`${apiUrl()}/compliance/packs/catalog`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (Array.isArray(d?.packs) && d.packs.length > 0) {
          setPackCatalog(d.packs as typeof PACK_CATALOG)
        }
      })
      .catch(() => {})
  }, [])

  // YAML preview modal
  const [yamlSlug, setYamlSlug] = useState<string | null>(null)
  const [yamlCache, setYamlCache] = useState<Map<string, string>>(new Map())
  const [yamlLoading, setYamlLoading] = useState(false)

  async function openYamlModal(slug: string) {
    setYamlSlug(slug)
    if (yamlCache.has(slug)) return
    setYamlLoading(true)
    try {
      const res = await fetch(`${apiUrl()}/workflows/playbooks/${slug}`)
      if (res.ok) {
        const data = await res.json()
        if (data.yaml_source) {
          setYamlCache(prev => new Map(prev).set(slug, data.yaml_source))
        }
      }
    } finally {
      setYamlLoading(false)
    }
  }

  // Install modal state
  const [pendingSlug, setPendingSlug] = useState<string | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string>("")
  const [projectsLoading, setProjectsLoading] = useState(false)
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [selectedEnvId, setSelectedEnvId] = useState<string>("")
  const [playbookInputs, setPlaybookInputs] = useState<Record<string, PlaybookInput>>({})
  const [inputValues, setInputValues] = useState<Record<string, string>>({})
  const [repos, setRepos] = useState<Repo[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string>("")
  const [reposLoading, setReposLoading] = useState(false)
  const [reposError, setReposError] = useState<string | null>(null)
  const [webhookError, setWebhookError] = useState<string | null>(null)
  const [lastInstalledId, setLastInstalledId] = useState<string | null>(null)
  const [agentName, setAgentName] = useState<string>("")

  async function authHeaders(): Promise<Record<string, string>> {
    const headers: Record<string, string> = {}
    if (getToken) {
      const token = await getToken()
      if (token) headers["Authorization"] = `Bearer ${token}`
    }
    const wsId = activeWorkspace?.id ?? null
    if (wsId) headers["X-Workspace-Id"] = wsId
    return headers
  }

  async function uninstallPlaybook(slug: string) {
    const wfId = installedWorkflowId.get(slug)
    if (!wfId) return
    const wsId = activeWorkspace?.id ?? null
    if (!wsId) return
    setUninstalling(slug)
    try {
      const h = await authHeaders()
      const res = await fetch(
        `${apiUrl()}/workflows/${wfId}?workspace_id=${wsId}`,
        { method: "DELETE", headers: h },
      )
      if (res.ok) {
        setInstalledCount(prev => { const m = new Map(prev); m.delete(slug); return m })
        setInstalledWorkflowId(prev => { const m = new Map(prev); m.delete(slug); return m })
      }
    } catch {}
    finally { setUninstalling(null) }
  }

  useEffect(() => {
    async function load() {
      const headers = await authHeaders()
      const workspaceId = activeWorkspace?.id ?? null
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const [pbRes, wfRes] = await Promise.all([
        fetch(`${apiUrl()}/workflows/playbooks`),
        fetch(`${apiUrl()}/workflows`, { headers }),
      ])

      let loadedPlaybooks: Playbook[] = []
      if (pbRes.ok) {
        loadedPlaybooks = await pbRes.json()
        setPlaybooks(loadedPlaybooks)
      }

      if (wfRes.ok) {
        const workflows: { id: string; name: string; playbook_slug?: string }[] = await wfRes.json()
        const counts = new Map<string, number>()
        const ids = new Map<string, string>()
        for (const wf of workflows) {
          if (wf.playbook_slug) {
            counts.set(wf.playbook_slug, (counts.get(wf.playbook_slug) ?? 0) + 1)
            if (!ids.has(wf.playbook_slug)) ids.set(wf.playbook_slug, wf.id)
          }
        }
        setInstalledCount(counts)
        setInstalledWorkflowId(ids)
      }

      // Submissions are newest-first. Unscored catalog entries have no row;
      // avoid one guaranteed 404 per playbook on a fresh deployment.
      if (loadedPlaybooks.length > 0) {
        const scoreHeaders = await authHeaders()
        const scoreMap = new Map<string, PlaybookScore>()
        try {
          const scoreResponse = await fetch(`${apiUrl()}/playbooks/submissions`, { headers: scoreHeaders })
          if (scoreResponse.ok) {
            const submissions: PlaybookScore[] = await scoreResponse.json()
            for (const score of submissions) {
              if (!scoreMap.has(score.slug)) scoreMap.set(score.slug, score)
            }
          }
        } catch { /* Optional scores must not keep the catalog loading. */ }
        setScores(scoreMap)
      }

      setLoading(false)
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function openInstallModal(slug: string) {
    setPendingSlug(slug)
    setAgentName(FRIENDLY_NAMES[slug] ?? slug)
    setProjectsLoading(true)
    try {
      const headers = await authHeaders()
      const workspaceId = activeWorkspace?.id ?? null
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const promises: Promise<void>[] = [
        fetch(`${apiUrl()}/workspaces/${workspaceId}/projects`, { headers }).then(async res => {
          if (res.ok) {
            const raw: Project[] = await res.json()
            const seen = new Set<string>()
            const data = raw.filter(p => {
              if (p.project_type && p.project_type !== "user") return false
              if (seen.has(p.id)) return false
              seen.add(p.id); return true
            })
            setProjects(data)
            setSelectedProjectId(data[0]?.id ?? "")
          }
        }),
        fetch(`${apiUrl()}/environments`, { headers }).then(async res => {
          if (res.ok) {
            const data: Environment[] = await res.json()
            setEnvironments(data)
            setSelectedEnvId(data[0]?.id ?? "")
          }
        }),
        fetch(`${apiUrl()}/workflows/playbooks/${slug}`).then(async res => {
          if (res.ok) {
            const data = await res.json()
            const inputs: Record<string, PlaybookInput> = data.inputs ?? {}
            setPlaybookInputs(inputs)
            setInputValues(Object.fromEntries(Object.entries(inputs).map(([k, v]) => [k, String(v.default ?? "")])))
          }
        }),
      ]

      // GitHub repo fetch is handled by the env-scoped useEffect below once selectedEnvId resolves.

      await Promise.all(promises)
    } finally {
      setProjectsLoading(false)
    }
  }

  function closeInstallModal() {
    setPendingSlug(null)
    setProjects([])
    setSelectedProjectId("")
    setEnvironments([])
    setSelectedEnvId("")
    setPlaybookInputs({})
    setInputValues({})
    setRepos([])
    setSelectedRepo("")
    setWebhookError(null)
  }

  // #735: refresh GitHub repos when selected environment changes.
  // Without this, the dropdown shows stale repos from a previous env's credential.
  useEffect(() => {
    if (!pendingSlug || !selectedEnvId) return
    if (!GITHUB_WEBHOOK_SLUGS.has(pendingSlug)) return
    let cancelled = false
    setReposLoading(true)
    setReposError(null)
    authHeaders().then(h =>
      fetch(`${apiUrl()}/credentials/github/repos?environment_id=${encodeURIComponent(selectedEnvId)}`, { headers: h })
        .then(async res => {
          if (cancelled) return
          if (!res.ok) {
            const body = await res.json().catch(() => ({}))
            const msg = body?.detail || `HTTP ${res.status}`
            setReposError(typeof msg === "string" ? msg : JSON.stringify(msg))
            setRepos([])
            setSelectedRepo("")
            return
          }
          const data: Repo[] = await res.json()
          setRepos(data)
          setSelectedRepo(data[0]?.full_name ?? "")
          if (data.length === 0) setReposError("Token is valid but no accessible repos returned. If you use a fine-grained PAT scoped to a single repo, GitHub's /user/repos may not list it, type the repo manually below.")
        })
        .catch((e) => { if (!cancelled) { setReposError(String(e)); setRepos([]); setSelectedRepo("") } })
        .finally(() => { if (!cancelled) setReposLoading(false) })
    )
    return () => { cancelled = true }
  }, [selectedEnvId, pendingSlug])

  async function confirmInstall() {
    if (!pendingSlug) return
    setInstalling(true)
    try {
      const headers = await authHeaders()
      headers["Content-Type"] = "application/json"
      const workspaceId = activeWorkspace?.id ?? null
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const needsRepo = GITHUB_WEBHOOK_SLUGS.has(pendingSlug)
      const body: Record<string, unknown> = {
        name: agentName.trim() || (FRIENDLY_NAMES[pendingSlug] ?? pendingSlug),
        template: pendingSlug,
      }
      if (selectedProjectId) body.project_id = selectedProjectId
      if (selectedEnvId) body.environment_id = selectedEnvId
      // New flow: repo is a normal input, declared in playbook YAML, substituted into the trigger.
      // Backend keeps body.repo as a backward-compat alias for old clients.
      const mergedInputs: Record<string, unknown> = { ...inputValues }
      if (needsRepo && selectedRepo) mergedInputs.repo = selectedRepo
      if (Object.keys(mergedInputs).length > 0) body.inputs = mergedInputs

      const res = await fetch(`${apiUrl()}/workflows`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setWebhookError(`Install failed: ${err.detail ?? res.status}`)
        return
      }
      const wf = await res.json()
      setInstalledCount(prev => new Map(prev).set(pendingSlug, (prev.get(pendingSlug) ?? 0) + 1))
      setLastInstalledId(wf.id)
      if (wf.webhook_error) {
        setWebhookError(wf.webhook_error)
      } else {
        closeInstallModal()
        router.push(`/workflows/${wf.id}`)
      }
    } finally {
      setInstalling(false)
    }
  }

  // Build category list from loaded playbooks, maintaining defined order
  const availableCategories = ["All", ...CATEGORY_ORDER.filter(c =>
    c !== "All" && playbooks.some(p => p.category === c)
  )]

  // Search filter
  const searchActive = search.trim().length > 0
  const searchFiltered = searchActive
    ? playbooks.filter(p =>
        (FRIENDLY_NAMES[p.slug] ?? p.name).toLowerCase().includes(search.toLowerCase()) ||
        p.description.toLowerCase().includes(search.toLowerCase())
      )
    : playbooks

  // Category filter (applied after search)
  const filtered = activeCategory === "All"
    ? searchFiltered
    : searchFiltered.filter(p => p.category === activeCategory)

  // Featured playbooks (shown only when no category filter and no search)
  const featuredPlaybooks = playbooks.filter(p => p.featured)
  const showFeatured = activeCategory === "All" && !searchActive && featuredPlaybooks.length > 0

  async function installPack(packId: string) {
    const wsId = activeWorkspace?.id ?? null
    if (!wsId || packInstalling) return
    setPackInstalling(packId)
    try {
      const token = getToken ? await getToken() : null
      const h: Record<string, string> = { "Content-Type": "application/json" }
      if (token) h["Authorization"] = `Bearer ${token}`
      const res = await fetch(`${apiUrl()}/compliance/packs/${packId}/install?workspace_id=${wsId}`, { method: "POST", headers: h })
      if (res.ok) setInstalledPacks(prev => new Set([...prev, packId]))
    } catch {}
    finally { setPackInstalling(null) }
  }

  async function uninstallPack(packId: string) {
    const wsId = activeWorkspace?.id ?? null
    if (!wsId || packInstalling) return
    setPackInstalling(packId)
    try {
      const token = getToken ? await getToken() : null
      const h: Record<string, string> = {}
      if (token) h["Authorization"] = `Bearer ${token}`
      const res = await fetch(`${apiUrl()}/compliance/packs/${packId}/uninstall?workspace_id=${wsId}`, { method: "DELETE", headers: h })
      if (res.ok) setInstalledPacks(prev => { const s = new Set(prev); s.delete(packId); return s })
    } catch {}
    finally { setPackInstalling(null) }
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-6 py-10">

        {/* Page header */}
        <div style={{ marginBottom: 20 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", letterSpacing: "-.02em", marginBottom: 5 }}>
            Registry
          </h1>
        </div>

        {/* Vertical sidebar + content layout */}
        <div style={{ display: "flex", gap: 0 }}>

          {/* Left sidebar */}
          <div style={{ width: 188, flexShrink: 0, borderRight: "1px solid var(--border)", paddingRight: 0, marginRight: 28 }}>
            <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".08em", padding: "0 10px 6px" }}>Agent Templates</div>
            {availableCategories.map(cat => {
              const active = marketTab === "templates" && activeCategory === cat
              return (
                <button key={cat}
                  onClick={() => { setMarketTab("templates"); setActiveCategory(cat); router.replace("/packs") }}
                  style={{
                    display: "block", width: "100%", textAlign: "left", padding: "7px 10px", borderRadius: 7,
                    background: active ? "var(--surface-2)" : "transparent",
                    color: active ? "var(--text)" : "var(--text-2)",
                    fontWeight: active ? 600 : 500, fontSize: 13, border: "none", cursor: "pointer",
                    marginBottom: 1, fontFamily: "inherit",
                  }}
                >
                  {CATEGORY_LABELS[cat] ?? cat}
                </button>
              )
            })}

            <div style={{ height: 1, background: "var(--border)", margin: "12px 10px" }} />

            <button onClick={() => { setMarketTab("modules"); router.replace("/packs?tab=modules") }}
              style={{
                display: "block", width: "100%", textAlign: "left", padding: "7px 10px", borderRadius: 7,
                background: marketTab === "modules" ? "var(--surface-2)" : "transparent",
                color: marketTab === "modules" ? "var(--text)" : "var(--text-2)",
                fontWeight: marketTab === "modules" ? 600 : 500, fontSize: 13, border: "none", cursor: "pointer",
                marginBottom: 1, fontFamily: "inherit",
              }}
            >
              Modules
            </button>

            <div style={{ height: 1, background: "var(--border)", margin: "12px 10px" }} />

            <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".08em", padding: "0 10px 6px" }}>Compliance</div>
            <button onClick={() => { setMarketTab("compliance"); router.replace("/packs?tab=compliance") }}
              style={{
                display: "block", width: "100%", textAlign: "left", padding: "7px 10px", borderRadius: 7,
                background: marketTab === "compliance" ? "var(--surface-2)" : "transparent",
                color: marketTab === "compliance" ? "var(--text)" : "var(--text-2)",
                fontWeight: marketTab === "compliance" ? 600 : 500, fontSize: 13, border: "none", cursor: "pointer",
                marginBottom: 1, fontFamily: "inherit",
              }}
            >
              Skill Packs
            </button>

            <div style={{ height: 1, background: "var(--border)", margin: "12px 10px" }} />

            <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".08em", padding: "0 10px 6px" }}>Connect</div>
            <button onClick={() => { setMarketTab("mcp"); router.replace("/packs?tab=mcp") }}
              style={{
                display: "block", width: "100%", textAlign: "left", padding: "7px 10px", borderRadius: 7,
                background: marketTab === "mcp" ? "var(--surface-2)" : "transparent",
                color: marketTab === "mcp" ? "var(--text)" : "var(--text-2)",
                fontWeight: marketTab === "mcp" ? 600 : 500, fontSize: 13, border: "none", cursor: "pointer",
                marginBottom: 1, fontFamily: "inherit",
              }}
            >
              MCP
            </button>
            <button onClick={() => { setMarketTab("proxy"); router.replace("/packs?tab=proxy") }}
              style={{
                display: "block", width: "100%", textAlign: "left", padding: "7px 10px", borderRadius: 7,
                background: marketTab === "proxy" ? "var(--surface-2)" : "transparent",
                color: marketTab === "proxy" ? "var(--text)" : "var(--text-2)",
                fontWeight: marketTab === "proxy" ? 600 : 500, fontSize: 13, border: "none", cursor: "pointer",
                marginBottom: 1, fontFamily: "inherit",
              }}
            >
              Proxy
            </button>
          </div>

          {/* Right content */}
          <div style={{ flex: 1, minWidth: 0 }}>

        {/* Modules tab */}
        {marketTab === "modules" && <ModulesManager />}

        {/* MCP tab */}
        {marketTab === "mcp" && <MCPConnectPanel />}

        {/* Proxy tab */}
        {marketTab === "proxy" && <ProxyConnectPanel />}

        {/* Skill Packs tab */}
        {marketTab === "compliance" && (
          <SkillPacksTab
            getToken={getToken}
            packCatalog={packCatalog}
            installedPacks={installedPacks}
            packInstalling={packInstalling}
            installPack={installPack}
            uninstallPack={uninstallPack}
          />
        )}

        {/* Agent Templates tab */}
        {marketTab === "templates" && <>
          <TemplatesTab
            search={search}
            setSearch={setSearch}
            loading={loading}
            showFeatured={showFeatured}
            featuredPlaybooks={featuredPlaybooks}
            filtered={filtered}
            installedCount={installedCount}
            installing={installing}
            openInstallModal={openInstallModal}
            openYamlModal={openYamlModal}
            scores={scores}
          />
        </>}

          </div>  {/* end right content */}
        </div>  {/* end sidebar+content flex */}
      </div>

      {/* YAML preview modal */}
      {yamlSlug && (
        <YamlModal
          yamlSlug={yamlSlug}
          setYamlSlug={setYamlSlug}
          yamlCache={yamlCache}
          yamlLoading={yamlLoading}
          openInstallModal={openInstallModal}
        />
      )}

      {/* Install modal */}
      {pendingSlug && (
        <InstallModal
          pendingSlug={pendingSlug}
          agentName={agentName}
          setAgentName={setAgentName}
          closeInstallModal={closeInstallModal}
          confirmInstall={confirmInstall}
          environments={environments}
          inputValues={inputValues}
          setInputValues={setInputValues}
          installing={installing}
          lastInstalledId={lastInstalledId}
          playbookInputs={playbookInputs}
          playbooks={playbooks}
          projects={projects}
          projectsLoading={projectsLoading}
          repos={repos}
          reposError={reposError}
          reposLoading={reposLoading}
          router={router}
          selectedEnvId={selectedEnvId}
          selectedProjectId={selectedProjectId}
          selectedRepo={selectedRepo}
          setSelectedEnvId={setSelectedEnvId}
          setSelectedProjectId={setSelectedProjectId}
          setSelectedRepo={setSelectedRepo}
          webhookError={webhookError}
        />
      )}
    </AppShell>
  )
}
