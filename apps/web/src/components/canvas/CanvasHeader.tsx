"use client"

import type { Dispatch, SetStateAction } from "react"
import { useRouter } from "next/navigation"
import type { Node } from "@xyflow/react"
import CostEstimate from "./CostEstimate"
import EnvDropdown from "./EnvDropdown"
import { usePreferences } from "@/lib/PreferencesContext"
import type { CanvasRuns, CanvasView, GetToken } from "./hooks/useCanvasRuns"

export type SaveStatus = "idle" | "saving" | "saved" | "error"

interface Props {
  workflowId: string
  getToken: GetToken
  isViewer: boolean
  nodes: Node[]
  workflowName: string
  setWorkflowName: (name: string) => void
  projectName: string | null
  playbookSlug: string | null
  environments: Array<{ id: string; name: string }>
  selectedEnvId: string
  envCredentials: Array<{ handle: string; service: string }>
  onEnvChange: (envId: string) => void
  activeView: CanvasView
  setActiveView: Dispatch<SetStateAction<CanvasView>>
  saveStatus: SaveStatus
  runs: CanvasRuns
}

export default function CanvasHeader({
  workflowId, getToken, isViewer, nodes, workflowName, setWorkflowName, projectName, playbookSlug,
  environments, selectedEnvId, envCredentials, onEnvChange, activeView, setActiveView, saveStatus, runs,
}: Props) {
  const router = useRouter()
  const { prefs } = usePreferences()
  return (
        <header className="flex items-center justify-between px-5 py-3 bg-white border-b border-stone-200 shrink-0">
          <div className="flex flex-col gap-0.5">
            <nav className="flex items-center gap-1 text-[10px] text-stone-400">
              {projectName ? (
                <>
                  <button onClick={() => router.push("/projects")} className="hover:text-stone-600 transition-colors">Projects</button>
                  <span>/</span>
                  <button onClick={() => router.back()} className="hover:text-stone-600 transition-colors max-w-[120px] truncate">{projectName}</button>
                  <span>/</span>
                  <span className="text-stone-500 font-medium max-w-[140px] truncate">{workflowName}</span>
                </>
              ) : (
                <>
                  <button onClick={() => router.push("/workflows")} className="hover:text-stone-600 transition-colors">← Workflows</button>
                  <span>/</span>
                  <span className="text-stone-500 font-medium max-w-[200px] truncate">{workflowName}</span>
                </>
              )}
            </nav>
          <div className="flex items-center gap-3">
            <input
              value={workflowName}
              onChange={(e) => !isViewer && setWorkflowName(e.target.value)}
              readOnly={isViewer}
              className="text-base font-semibold text-stone-900 bg-transparent border-none outline-none focus:ring-0 w-64"
            />
            {/* Environment picker with integration status */}
            <EnvDropdown
              environments={environments}
              selectedEnvId={selectedEnvId}
              credentials={envCredentials}
              nodes={nodes}
              disabled={isViewer}
              onChange={id => !isViewer && onEnvChange(id)}
            />
            <div className="ml-3 flex bg-stone-100 rounded-md p-0.5 text-xs">
              {(["canvas", "definition", "runs", "settings"] as const).map(v => (
                <button
                  key={v}
                  onClick={() => setActiveView(v)}
                  className={`px-2.5 py-1 rounded capitalize ${
                    activeView === v
                      ? "bg-white text-stone-900 shadow-sm font-medium"
                      : "text-stone-500 hover:text-stone-800"
                  }`}
                >
                  {v === "canvas" ? "Canvas" : v === "definition" ? "Definition" : v === "runs" ? "Runs" : "Settings"}
                </button>
              ))}
            </div>
          </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Autosave status */}
            <span className={`text-xs transition-opacity duration-300 ${
              saveStatus === "saving" ? "text-amber-500 opacity-100" :
              saveStatus === "saved"  ? "text-green-500 opacity-100" :
              saveStatus === "error"  ? "text-red-500 opacity-100" :
              "opacity-0"
            }`}>
              {saveStatus === "saving" ? "Saving…" : saveStatus === "error" ? "Save failed" : "Saved ✓"}
            </span>
            <CostEstimate workflowId={workflowId} nodes={nodes} getToken={getToken} />

            {!isViewer && (
              <>
                {prefs.show_test_trigger && playbookSlug && (
                  <button
                    onClick={() => runs.setTestTriggerModal(true)}
                    disabled={runs.running !== "idle" || runs.testRunning}
                    className="rounded-lg border border-emerald-200 px-3 py-1.5 text-xs font-medium text-emerald-600 hover:bg-emerald-50 transition-colors disabled:opacity-50"
                  >
                    {runs.testRunning ? "Starting…" : "⚗ Dry Run"}
                  </button>
                )}
                {prefs.show_dry_run && (
                  <button
                    onClick={() => runs.startRun(true)}
                    disabled={runs.running !== "idle"}
                    className="rounded-lg border border-stone-200 px-3 py-1.5 text-xs font-medium text-stone-500 hover:bg-stone-50 transition-colors disabled:opacity-50"
                  >
                    {runs.running === "dry" ? "Simulating…" : "Dry run"}
                  </button>
                )}
                {runs.activeRunId && !runs.drawerVisible && (
                  <button
                    onClick={() => runs.setDrawerVisible(true)}
                    className="rounded-lg border border-violet-300 px-3 py-1.5 text-xs font-medium text-violet-700 hover:bg-violet-50 transition-colors"
                  >
                    View output ↑
                  </button>
                )}
                <button
                  onClick={() => runs.startRun(false)}
                  disabled={runs.running === "live" || runs.running === "dry"}
                  className="rounded-lg bg-violet-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-violet-700 transition-colors disabled:opacity-50"
                >
                  {runs.running === "live" ? "Starting…" : runs.running === "dry" ? "Simulating…" : "▶ Run"}
                </button>
              </>
            )}
          </div>
        </header>
  )
}
