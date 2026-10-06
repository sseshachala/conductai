import { useCallback, useEffect, useRef, useState } from "react"
import type { Node } from "@xyflow/react"
import type { BlockNodeData } from "../BlockNode"
import { workflows } from "@/lib/api"
import type { AuthFetch } from "@/lib/api"
import { validateNodes, type ValidationError } from "@/lib/canvas/validateNodes"
import { resolveIssueTriggerState } from "@/lib/canvas/issueTrigger"

export type GetToken = (() => Promise<string | null>) | null | undefined
export type CanvasView = "canvas" | "definition" | "runs" | "settings"
export type RunListItem = { id: string; status: string; triggered_by: string | null; created_at: string }
export type Preflight = { suggestedTurns: number; files: string[]; pendingDryRun: boolean; initialState?: Record<string, unknown> }

const TERMINAL = new Set(["succeeded", "failed", "cancelled"])

export async function authHeaders(getToken: GetToken, wsId?: string | null): Promise<Record<string, string>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (getToken) {
    const token = await getToken()
    if (token) headers["Authorization"] = `Bearer ${token}`
  }
  if (wsId) headers["X-Workspace-Id"] = wsId
  return headers
}

export function makeAuthFetch(headers: Record<string, string>, signal?: AbortSignal): AuthFetch {
  return (url, opts) => fetch(url, { signal, ...opts, headers: { ...headers, ...(opts?.headers as Record<string, string> | undefined) } })
}

function findTrigger(nodes: Node[], match: (eventType: unknown) => boolean): Node | undefined {
  return nodes.find(n => {
    const d = n.data as BlockNodeData
    return d.type === "trigger" && match(((d.config as Record<string, unknown>) ?? {}).event_type)
  })
}

interface Options {
  workflowId: string
  getToken: GetToken
  wsId: string | null
  nodes: Node[]
  setNodes: (updater: (nds: Node[]) => Node[]) => void
  selectedEnvId: string
  githubHookRepo: string | null
  activeView: CanvasView
  setActiveView: (v: CanvasView) => void
  navigate: (href: string) => void
}

/** Run lifecycle for the canvas: launching, preflight, polling, history. */
export function useCanvasRuns({ workflowId, getToken, wsId, nodes, setNodes, selectedEnvId, githubHookRepo, activeView, setActiveView, navigate }: Options) {
  const [running, setRunning] = useState<"idle" | "dry" | "live">("idle")
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [drawerVisible, setDrawerVisible] = useState(false)
  const [validationErrors, setValidationErrors] = useState<ValidationError[]>([])
  const [preflight, setPreflight] = useState<Preflight | null>(null)
  const [runs, setRuns] = useState<RunListItem[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  // Webhook test modal — shown when manually running a webhook-triggered workflow
  const [webhookModal, setWebhookModal] = useState<{ dryRun: boolean } | null>(null)
  const [webhookRepo, setWebhookRepo] = useState("")
  const [webhookPrNumber, setWebhookPrNumber] = useState("")
  const [testTriggerModal, setTestTriggerModal] = useState(false)
  const [testRunning, setTestRunning] = useState(false)
  // #734 pre-run modal — opens when /trigger returns 422 missing_required_inputs
  const [inputsModalPayload, setInputsModalPayload] = useState<Record<string, unknown> | null>(null)
  const [testRunId, setTestRunId] = useState<string | null>(null)
  const [testRunStatus, setTestRunStatus] = useState<string | null>(null)
  const [lastRunState, setLastRunState] = useState<Record<string, Record<string, unknown>> | undefined>(undefined)
  const [lastRunSummary, setLastRunSummary] = useState<{ status: string; created_at?: string; run_id?: string } | undefined>(undefined)
  const [testPrNumber, setTestPrNumber] = useState("")
  const [testMaxTurns, setTestMaxTurns] = useState("")
  const [runError, setRunError] = useState<string | null>(null)

  const STORAGE_KEY = `marshal:active-run:${workflowId}`
  const TEST_RUN_KEY = `marshal:test-run:${workflowId}`
  const isMountedRef = useRef(true)
  useEffect(() => () => { isMountedRef.current = false }, [])

  const showRunError = (e: unknown) => {
    setRunning("idle")
    setRunError(e instanceof Error ? e.message : "Failed to start run — check your connection.")
    setTimeout(() => setRunError(null), 6000)
  }

  // On mount, check if there's an in-progress run we navigated away from.
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return
    const { runId, startedAt } = JSON.parse(stored)
    // Ignore stale entries older than 2 hours
    if (Date.now() - startedAt > 2 * 60 * 60 * 1000) {
      localStorage.removeItem(STORAGE_KEY)
      return
    }
    const abort = new AbortController()
    ;(async () => {
      try {
        const headers = await authHeaders(getToken, wsId)
        if (abort.signal.aborted) return
        const run = await workflows.runs.get(makeAuthFetch(headers, abort.signal), workflowId, runId).catch(() => null)
        if (!run) { localStorage.removeItem(STORAGE_KEY); return }
        if (abort.signal.aborted) return
        if (run.status === "running" || run.status === "pending") {
          setActiveRunId(runId)
          setDrawerVisible(true)
        } else {
          localStorage.removeItem(STORAGE_KEY)
        }
      } catch {
        localStorage.removeItem(STORAGE_KEY)
      }
    })()
    return () => abort.abort()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId])

  // Restore test run banner on mount + poll status until terminal
  useEffect(() => {
    const stored = localStorage.getItem(TEST_RUN_KEY)
    if (!stored) return
    setTestRunId(JSON.parse(stored).runId)
    setTestRunStatus("pending")
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId])

  useEffect(() => {
    if (!testRunId) return
    if (testRunStatus && TERMINAL.has(testRunStatus)) return
    const poll = async () => {
      try {
        const run = await workflows.runs.get(makeAuthFetch(await authHeaders(getToken, wsId)), workflowId, testRunId)
        setTestRunStatus(run.status)
        // Feed live state into Definition panel as blocks complete
        if (run.state) setLastRunState(run.state)
        setLastRunSummary({ status: run.status, created_at: run.created_at, run_id: run.id })
        if (TERMINAL.has(run.status)) localStorage.removeItem(TEST_RUN_KEY)
      } catch {}
    }
    poll()
    const interval = setInterval(poll, 2000)
    return () => clearInterval(interval)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testRunId, testRunStatus])

  const fetchRuns = () => {
    if (!workflowId) return
    setRunsLoading(true)
    authHeaders(getToken, wsId)
      .then(headers => workflows.runs.list(makeAuthFetch(headers), workflowId, { limit: 50 }))
      .then(data => setRuns(data))
      .catch(() => {})
      .finally(() => setRunsLoading(false))
  }

  useEffect(() => {
    if (activeView === "runs") fetchRuns()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView, workflowId, getToken])

  // Auto-poll every 5s while any run is active
  useEffect(() => {
    if (activeView !== "runs") return
    if (!runs.some(r => r.status === "pending" || r.status === "running")) return
    const t = setInterval(fetchRuns, 5000)
    return () => clearInterval(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView, runs])

  // Poll live run state for the active (non-dry) run — feeds Definition panel
  useEffect(() => {
    if (!activeRunId) return
    let stopped = false
    const poll = async () => {
      if (stopped) return
      try {
        const run = await workflows.runs.get(makeAuthFetch(await authHeaders(getToken, wsId)), workflowId, activeRunId)
        if (stopped) return
        setLastRunState(run.state ?? {})
        setLastRunSummary({ status: run.status, created_at: run.created_at, run_id: run.id })
        if (TERMINAL.has(run.status)) stopped = true
      } catch {}
    }
    poll()
    const interval = setInterval(poll, 2000)
    return () => { stopped = true; clearInterval(interval) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRunId])

  // Fetch last run state when Definition tab is active
  useEffect(() => {
    if (activeView !== "definition" || !workflowId) return
    const abort = new AbortController()
    ;(async () => {
      try {
        const headers = await authHeaders(getToken, wsId)
        if (abort.signal.aborted) return
        const authFetch = makeAuthFetch(headers, abort.signal)
        const [latest] = await workflows.runs.list(authFetch, workflowId, { limit: 1 })
        if (!latest || abort.signal.aborted) return
        const full = await workflows.runs.get(authFetch, workflowId, latest.id)
        if (abort.signal.aborted) return
        setLastRunSummary({ status: full.status, created_at: full.created_at, run_id: full.id })
        setLastRunState(full.state ?? {})
      } catch { /* silent */ }
    })()
    return () => abort.abort()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView, workflowId])

  /** Drawer fallback when the server didn't mint a Lens session (or webhook runs). */
  const openRunInDrawer = (runId: string) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ runId, startedAt: Date.now() }))
    setActiveRunId(runId)
    setDrawerVisible(true)
    setRunning("idle")
    setLastRunSummary({ status: "pending", created_at: new Date().toISOString(), run_id: runId })
    setActiveView("definition")
  }

  const fireRun = async (dryRun: boolean, initialState: Record<string, unknown> | undefined, maxTurns: number | undefined) => {
    const res = await workflows.runs.trigger(makeAuthFetch(await authHeaders(getToken, wsId)), workflowId, {
      triggered_by: "manual",
      dry_run: dryRun,
      // #1515 — non-dry canvas runs land in a Lens session; the RunBubble
      // auto-spawns via the #1502 rehydration path. Dry runs keep the old
      // /workflows/{id}/runs/{id} inspector page.
      create_lens_session: !dryRun,
      ...(initialState ? { initial_state: initialState } : {}),
      ...(maxTurns    ? { max_turns: maxTurns }          : {}),
    })
    if (!res.ok) throw new Error("Failed to start run")
    const run = await res.json()
    if (dryRun) {
      navigate(`/workflows/${workflowId}/runs/${run.id}`)
    } else if (run.session_id) {
      // Keep localStorage marker so a return to canvas still shows "recent run" affordances.
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ runId: run.id, startedAt: Date.now() }))
      navigate(`/lens/${run.session_id}`)
    } else {
      openRunInDrawer(run.id)
    }
  }

  const startRun = async (dryRun: boolean) => {
    // Client-side quick checks first
    if (!selectedEnvId) {
      setValidationErrors([{ blockId: "__env__", label: "Vault", message: "Select a vault before running — add one in Settings → Vault" }])
      return
    }
    const localErrors = validateNodes(nodes)
    if (localErrors.length > 0) { setValidationErrors(localErrors); return }
    setValidationErrors([])
    setRunning(dryRun ? "dry" : "live")

    // Server-side pre-flight: credentials, brain descriptions, required fields
    try {
      const vRes = await workflows.validate(makeAuthFetch(await authHeaders(getToken, wsId)), workflowId, {})
      if (vRes.ok) {
        const { valid, errors } = await vRes.json()
        if (!valid) {
          setValidationErrors(errors.map((e: { block_id: string; label: string; message: string }) => ({ blockId: e.block_id, label: e.label, message: e.message })))
          setRunning("idle")
          return
        }
      }
    } catch {
      setRunning("idle")
      return
    }

    try {
      const authFetch = makeAuthFetch(await authHeaders(getToken, wsId))
      let initialState: Record<string, unknown> | undefined
      const triggerNode = findTrigger(nodes, t => t === "github_issue_labeled" || t === "github_issue")
      const webhookTriggerNode = findTrigger(nodes, t => t === "webhook")

      // Webhook trigger — prompt for PR details before running
      if (webhookTriggerNode && !triggerNode) {
        const cfg = (webhookTriggerNode.data as BlockNodeData).config as Record<string, unknown>
        // Use github_hook_repo (authoritative) — test_repo is removed
        setWebhookRepo(githubHookRepo || "")
        setWebhookPrNumber((cfg.test_pr_number as string) || "")
        setRunning("idle")
        setWebhookModal({ dryRun })
        return
      }

      if (triggerNode) {
        const result = await resolveIssueTriggerState(authFetch, triggerNode, selectedEnvId)
        if ("error" in result) { setValidationErrors([result.error]); setRunning("idle"); return }
        initialState = result.initialState
      }

      // Preflight: estimate turn budget using Claude (cheap single call per brain block)
      const issue = initialState?.github_issue as Record<string, string> | undefined
      try {
        const pfRes = await workflows.preflight(authFetch, workflowId, {
          issue_title: issue?.title ?? "",
          issue_body:  issue?.body  ?? "",
          run_inputs: initialState ?? {},
        })
        if (pfRes.ok) {
          const pf = await pfRes.json()
          if (pf.suggested_max_turns > 20) {
            setPreflight({ suggestedTurns: pf.suggested_max_turns, files: pf.total_files ?? [], pendingDryRun: dryRun, initialState })
            setRunning("idle")
            return
          }
        }
      } catch { /* preflight is best-effort */ }

      await fireRun(dryRun, initialState ?? { __manual: true }, undefined)
    } catch (e) {
      showRunError(e)
    }
  }

  const confirmPreflight = async (maxTurns: number | undefined) => {
    if (!preflight) return
    setPreflight(null)
    setRunning(preflight.pendingDryRun ? "dry" : "live")
    try {
      await fireRun(preflight.pendingDryRun, preflight.initialState ?? { __manual: true }, maxTurns)
    } catch (e) {
      showRunError(e)
    }
  }

  const cancelPreflight = () => { setPreflight(null); setRunning("idle") }

  const startWebhookRun = async (dryRun: boolean, repo: string, prNumber: string) => {
    setWebhookModal(null)
    setRunning(dryRun ? "dry" : "live")
    try {
      const [owner, repoName] = repo.split("/")
      const num = parseInt(prNumber, 10)
      const initialState = {
        _trigger: {
          action: "opened",
          number: num,
          repository: { full_name: repo, name: repoName, owner: { login: owner } },
          pull_request: {
            number: num,
            title: `Test PR #${num}`,
            user: { login: "test-user", type: "User" },
            html_url: `https://github.com/${repo}/pull/${num}`,
            diff_url: `https://github.com/${repo}/pull/${num}.diff`,
            base: { ref: "main" },
            head: { ref: `test-branch-${num}` },
          },
        },
      }
      const res = await workflows.runs.trigger(makeAuthFetch(await authHeaders(getToken, wsId)), workflowId, { triggered_by: "manual", dry_run: dryRun, initial_state: initialState })
      if (!res.ok) throw new Error("Failed to start run")
      const run = await res.json()
      if (!isMountedRef.current) return
      openRunInDrawer(run.id)
    } catch (e) {
      if (isMountedRef.current) showRunError(e)
    }
  }

  const performTestTrigger = async (payload: Record<string, unknown>) => {
    // #1515 P1 — backend auto-mints a Lens session when lens_attach=true.
    const res = await workflows.trigger(makeAuthFetch(await authHeaders(getToken, wsId)), workflowId, { ...payload, lens_attach: true })
    if (res.status === 422) {
      const errBody = await res.json().catch(() => null)
      if (errBody?.detail?.error === "missing_required_inputs") {
        setInputsModalPayload(payload)
        return
      }
    }
    if (!res.ok) throw new Error("Failed to start test run")
    const data = await res.json()
    localStorage.setItem(TEST_RUN_KEY, JSON.stringify({ runId: data.run_id, startedAt: Date.now() }))
    setTestRunId(data.run_id)
    setTestRunStatus("pending")
    setLastRunSummary({ status: "pending", created_at: new Date().toISOString(), run_id: data.run_id })
    setActiveView("definition")
    // #1515 P1 — redirect to the Lens session so the RunBubble renders with live SSE.
    if (data.session_id) navigate(`/lens/${data.session_id}`)
  }

  const startTestTrigger = async () => {
    setTestTriggerModal(false)
    setTestRunning(true)
    setTestRunId(null)
    try {
      const payload: Record<string, unknown> = {}
      if (testPrNumber.trim()) {
        const pr = parseInt(testPrNumber.trim(), 10)
        const repo = githubHookRepo ?? ""
        payload.number = pr
        payload.pull_request = {
          number: pr,
          html_url: repo ? `https://github.com/${repo}/pull/${pr}` : "",
          diff_url: repo ? `https://github.com/${repo}/pull/${pr}.diff` : "",
          title: `PR #${pr}`,
          user: { login: "" },
          base: { ref: "main" },
          head: { ref: "" },
        }
      }
      const turns = parseInt(testMaxTurns.trim(), 10)
      if (!isNaN(turns) && turns > 0) payload.__max_turns_override = turns
      await performTestTrigger(payload)
    } catch {
      // test run failed to start — setTestRunning resets below
    } finally {
      setTestRunning(false)
    }
  }

  const confirmInputs = async (newInputs: Record<string, unknown>) => {
    const payload = { ...inputsModalPayload, inputs: newInputs }
    setInputsModalPayload(null)
    try { await performTestTrigger(payload) } catch { /* surfaced via existing state */ }
    finally { setTestRunning(false) }
  }

  const cancelInputs = () => { setInputsModalPayload(null); setTestRunning(false) }

  const dismissTestRun = () => { localStorage.removeItem(TEST_RUN_KEY); setTestRunId(null); setTestRunStatus(null) }

  const handleBlockStatus = useCallback((blockId: string, status: "running" | "completed" | "failed" | "skipped") => {
    setNodes(nds => nds.map(n =>
      n.id === blockId ? { ...n, data: { ...n.data, runStatus: status, ...(status === "running" ? { liveTurn: undefined } : {}) } } : n
    ))
  }, [setNodes])

  const handleBlockTurns = useCallback((blockId: string, turn: number) => {
    setNodes(nds => nds.map(n => (n.id === blockId ? { ...n, data: { ...n.data, liveTurn: turn } } : n)))
  }, [setNodes])

  const hideDrawer = useCallback(() => setDrawerVisible(false), [])

  const onRunDone = () => { localStorage.removeItem(STORAGE_KEY); setRunning("idle"); setActiveRunId(null) }

  return {
    running, activeRunId, drawerVisible, setDrawerVisible, validationErrors, setValidationErrors,
    preflight, confirmPreflight, cancelPreflight, runs, runsLoading, fetchRuns,
    webhookModal, setWebhookModal, webhookRepo, setWebhookRepo, webhookPrNumber, setWebhookPrNumber, startWebhookRun,
    testTriggerModal, setTestTriggerModal, testRunning, testPrNumber, setTestPrNumber, testMaxTurns, setTestMaxTurns, startTestTrigger,
    inputsModalPayload, confirmInputs, cancelInputs, testRunId, testRunStatus, dismissTestRun,
    lastRunState, lastRunSummary, runError, setRunError, startRun,
    handleBlockStatus, handleBlockTurns, hideDrawer, onRunDone,
  }
}

export type CanvasRuns = ReturnType<typeof useCanvasRuns>
