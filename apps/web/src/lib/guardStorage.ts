// Multi-workspace Guard team ID storage.
// guard_teams: { [workspaceId]: teamId }
// guard_active_workspace: last workspace with Guard active (for pages without workspace context)

export function getGuardTeamId(workspaceId?: string): string {
  if (typeof window === "undefined") return ""
  const wsId = workspaceId ?? localStorage.getItem("guard_active_workspace") ?? ""
  const teams: Record<string, string> = JSON.parse(localStorage.getItem("guard_teams") || "{}")
  if (wsId && teams[wsId]) return teams[wsId]
  return localStorage.getItem("guard_team_id") ?? "" // legacy fallback for existing installs
}

export function setGuardTeamId(workspaceId: string, teamId: string): void {
  const teams: Record<string, string> = JSON.parse(localStorage.getItem("guard_teams") || "{}")
  teams[workspaceId] = teamId
  localStorage.setItem("guard_teams", JSON.stringify(teams))
  localStorage.setItem("guard_active_workspace", workspaceId)
}

export function removeGuardTeamId(workspaceId: string): void {
  const teams: Record<string, string> = JSON.parse(localStorage.getItem("guard_teams") || "{}")
  delete teams[workspaceId]
  localStorage.setItem("guard_teams", JSON.stringify(teams))
  if (localStorage.getItem("guard_active_workspace") === workspaceId) {
    localStorage.removeItem("guard_active_workspace")
  }
}

export function setActiveGuardWorkspace(workspaceId: string): void {
  localStorage.setItem("guard_active_workspace", workspaceId)
}
