"use client"

import type { Dispatch, SetStateAction } from "react"
import type { useRouter } from "next/navigation"
import {
  FRIENDLY_NAMES, GITHUB_WEBHOOK_SLUGS, MANUAL_WEBHOOK_SLUGS, MODEL_HINTS,
  type Environment, type Playbook, type PlaybookInput, type Project, type Repo,
} from "./catalog"

// Install modal
export function InstallModal({
  pendingSlug, agentName, setAgentName, closeInstallModal, confirmInstall, environments, inputValues, setInputValues, installing, lastInstalledId, playbookInputs, playbooks, projects, projectsLoading, repos, reposError, reposLoading, router, selectedEnvId, selectedProjectId, selectedRepo, setSelectedEnvId, setSelectedProjectId, setSelectedRepo, webhookError,
}: {
  pendingSlug: string
  agentName: string
  setAgentName: Dispatch<SetStateAction<string>>
  closeInstallModal: () => void
  confirmInstall: () => Promise<void>
  environments: Environment[]
  inputValues: Record<string, string>
  setInputValues: Dispatch<SetStateAction<Record<string, string>>>
  installing: boolean
  lastInstalledId: string | null
  playbookInputs: Record<string, PlaybookInput>
  playbooks: Playbook[]
  projects: Project[]
  projectsLoading: boolean
  repos: Repo[]
  reposError: string | null
  reposLoading: boolean
  router: ReturnType<typeof useRouter>
  selectedEnvId: string
  selectedProjectId: string
  selectedRepo: string
  setSelectedEnvId: Dispatch<SetStateAction<string>>
  setSelectedProjectId: Dispatch<SetStateAction<string>>
  setSelectedRepo: Dispatch<SetStateAction<string>>
  webhookError: string | null
}) {
  return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 p-6 flex flex-col gap-5 max-h-[90vh] overflow-y-auto">
            <div>
              <h2 className="text-sm font-semibold text-stone-900">Install to project</h2>
              <p className="text-xs text-stone-400 mt-1">
                Choose where to install <span className="font-medium text-stone-600">{FRIENDLY_NAMES[pendingSlug] ?? pendingSlug}</span>.
              </p>
            </div>

            {/* Agent name */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-stone-500">Workflow name</label>
              <input
                type="text"
                value={agentName}
                onChange={e => setAgentName(e.target.value)}
                placeholder={FRIENDLY_NAMES[pendingSlug ?? ""] ?? pendingSlug ?? ""}
                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
              />
              <p className="text-[10px] text-stone-400">Give this instance a name, e.g. "Autopilot, conductai prod"</p>
            </div>

            {/* Project picker */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-stone-500">Project</label>
              {projectsLoading ? (
                <div className="h-9 rounded-lg bg-stone-100 animate-pulse" />
              ) : (
                <select
                  value={selectedProjectId}
                  onChange={e => setSelectedProjectId(e.target.value)}
                  className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                >
                  {projects.map(p => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              )}
            </div>

            {/* Environment picker */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-stone-500">Environment</label>
              {environments.length === 0 ? (
                <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                  No vaults found. <a href="/settings?tab=credentials" className="underline font-medium">Create one first</a>.
                </div>
              ) : (
                <select
                  value={selectedEnvId}
                  onChange={e => setSelectedEnvId(e.target.value)}
                  className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                >
                  {environments.map(e => (
                    <option key={e.id} value={e.id}>{e.name}</option>
                  ))}
                </select>
              )}
            </div>

            {/* Playbook inputs — only skip `repo` when the GitHub repo picker below will render it (webhook-triggered playbooks). Non-webhook playbooks that declare inputs.repo still need a field. */}
            {Object.entries(playbookInputs).filter(([key]) => !(key === "repo" && GITHUB_WEBHOOK_SLUGS.has(pendingSlug))).map(([key, input]) => (
              <div key={key} className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-stone-500">
                  {input.label ?? key}
                  {input.hint && <span className="ml-1 font-normal text-stone-400">— {input.hint}</span>}
                </label>
                {input.type === "select" && input.options ? (
                  <>
                    <select
                      value={inputValues[key] ?? String(input.default ?? "")}
                      onChange={e => setInputValues(prev => ({ ...prev, [key]: e.target.value }))}
                      className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                    >
                      {input.options.map(opt => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </select>
                    {key === "model" && (
                      <p className="text-xs text-stone-400">
                        {MODEL_HINTS[inputValues["model"] ?? String(input.default ?? "")] ?? ""}
                      </p>
                    )}
                  </>
                ) : (
                  <input
                    type="text"
                    value={inputValues[key] ?? String(input.default ?? "")}
                    onChange={e => setInputValues(prev => ({ ...prev, [key]: e.target.value }))}
                    className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                  />
                )}
              </div>
            ))}

            {/* Repo picker. GitHub webhook playbooks */}
            {GITHUB_WEBHOOK_SLUGS.has(pendingSlug) && (
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-stone-500">
                  GitHub repo
                  <span className="ml-1 text-stone-400 font-normal">— webhook registered automatically on install</span>
                </label>
                {reposLoading ? (
                  <div className="h-9 rounded-lg bg-stone-100 animate-pulse" />
                ) : (
                  <>
                    {reposError && (
                      <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-2">
                        {reposError}
                      </div>
                    )}
                    {repos.length === 1 ? (
                      <div className="text-xs text-stone-700 bg-stone-50 border border-stone-200 rounded-lg px-3 py-2">
                        Selected <span className="font-medium">{repos[0].full_name}</span>, the only repo your GitHub token can access.
                      </div>
                    ) : repos.length > 1 ? (
                      <select
                        value={selectedRepo}
                        onChange={e => setSelectedRepo(e.target.value)}
                        className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                      >
                        {repos.map(r => (
                          <option key={r.full_name} value={r.full_name}>{r.full_name}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="text"
                        value={selectedRepo}
                        onChange={e => setSelectedRepo(e.target.value)}
                        placeholder="owner/repo"
                        className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
                      />
                    )}
                  </>
                )}
              </div>
            )}

            {/* Manual setup instructions, inbound webhook playbooks */}
            {MANUAL_WEBHOOK_SLUGS.has(pendingSlug) && (
              <div className="bg-stone-50 border border-stone-200 rounded-lg px-3 py-3 flex flex-col gap-1.5">
                <p className="text-xs font-medium text-stone-700">Manual webhook setup required</p>
                <p className="text-xs text-stone-500 leading-relaxed">
                  After installing, copy the webhook URL from the workflow settings and paste it into your{" "}
                  PagerDuty, OpsGenie, or incident management tool.
                </p>
              </div>
            )}

            {webhookError && (
              <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-3">
                <p className="text-xs font-semibold text-red-700 mb-1">Webhook not registered</p>
                <p className="text-xs text-red-600 leading-relaxed">{webhookError}</p>
                <p className="text-xs text-stone-400 mt-2">The agent was installed, the webhook can be added once the token is updated.</p>
                <button onClick={() => { closeInstallModal(); router.push(`/workflows/${lastInstalledId ?? ""}`) }}
                  className="mt-2 text-xs underline text-red-700">Open agent anyway →</button>
              </div>
            )}

            <div className="flex gap-2 justify-end">
              <button
                onClick={closeInstallModal}
                className="px-4 py-2 text-xs text-stone-500 hover:text-stone-700 rounded-lg hover:bg-stone-100 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmInstall}
                disabled={installing || projectsLoading || environments.length === 0}
                className="px-4 py-2 text-xs font-medium bg-stone-900 text-white rounded-lg hover:bg-stone-700 disabled:opacity-40 transition-colors"
              >
                {installing ? "Installing…" : "Install"}
              </button>
            </div>
          </div>
        </div>
  )
}
