import type { Node } from "@xyflow/react"
import type { BlockNodeData } from "@/components/canvas/BlockNode"
import type { AuthFetch } from "@/lib/api"
import { API as API_URL } from "@/lib/api/client"
import type { ValidationError } from "./validateNodes"

type IssueTriggerResult =
  | { initialState: Record<string, unknown> }
  | { error: ValidationError }

/** Translate known GitHub errors into actionable user-facing text. */
function friendlyIssueError(status: number, serverDetail: string, repo: string): string {
  if (status === 404) {
    return `No GitHub credential connected for this workspace. Add one in Settings → Vault and reload.`
  }
  if (/Resource not accessible by personal access token/i.test(serverDetail)) {
    return `Your GitHub token does not have permission to read issues on ${repo}. Fine-grained PAT: grant Repository → ${repo} and Permissions → Issues (Read). Classic PAT: include the 'repo' scope (private) or 'public_repo' scope (public). Then reconnect in Settings → Vault.`
  }
  if (/Bad credentials/i.test(serverDetail)) {
    return `GitHub rejected your token as invalid or expired. Reconnect in Settings → Vault.`
  }
  if (/API rate limit exceeded/i.test(serverDetail)) {
    return `GitHub API rate limit hit. Wait a few minutes or use an authenticated token with higher limits.`
  }
  // Fallback — show the raw error if we don't have a translation
  return `GitHub returned HTTP ${status}${serverDetail ? `: ${serverDetail.slice(0, 200)}` : ""}`
}

/**
 * Replicates what the CLI does for issue-labeled triggers: query GitHub for a
 * matching open issue and build the run's initial_state from it.
 */
export async function resolveIssueTriggerState(
  authFetch: AuthFetch,
  triggerNode: Node,
  selectedEnvId: string,
): Promise<IssueTriggerResult> {
  const data = triggerNode.data as BlockNodeData
  const cfg = (data.config as Record<string, unknown>) ?? {}
  const fail = (message: string): IssueTriggerResult => ({ error: { blockId: triggerNode.id, label: data.label, message } })

  const repoAllowlist = (cfg.repo_allowlist as string) || ""
  // Canvas stores labels as an array at cfg.labels — the only canonical path.
  const labelsArr: string[] = Array.isArray(cfg.labels)
    ? (cfg.labels as string[]).map(s => String(s).trim()).filter(Boolean)
    : []
  const label = labelsArr[0] || ""
  const repo = repoAllowlist.split(",").map(s => s.trim()).filter(Boolean)[0] // try first configured repo

  if (!repo || !label) {
    const missing: string[] = []
    if (!repo) missing.push("Repository")
    if (!label) missing.push("Label")
    return fail(`Set ${missing.join(" and ")} on the trigger block before running`)
  }

  // Pass environment_id so the credential lookup uses the workflow's env,
  // not whichever workspace-level GitHub token comes back first.
  const issueParams = new URLSearchParams({ repo, label })
  if (selectedEnvId) issueParams.set("environment_id", selectedEnvId)
  const issueRes = await authFetch(`${API_URL}/credentials/github/issues?${issueParams.toString()}`)
  if (!issueRes.ok) {
    // Read server detail + GitHub message buried inside it
    let serverDetail = ""
    try {
      const body = await issueRes.json()
      serverDetail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body)
    } catch {
      try { serverDetail = await issueRes.text() } catch { /* give up */ }
    }
    return fail(friendlyIssueError(issueRes.status, serverDetail, repo))
  }

  const issues: Array<{ number: number; title: string; body: string; url: string; author: string; labels: string[]; clone_url: string }> = await issueRes.json()
  if (issues.length === 0) {
    return fail(`No open issues with label "${label}" found in ${repo}`)
  }

  // Multiple matching issues — pick the most recent (GitHub returns by
  // created_at DESC) and proceed. Production webhook fires one run per
  // labeling event anyway; this is just a manual test fire.
  const issue = issues[0]
  if (issues.length > 1) {
    console.info(
      `[canvas] ${issues.length} issues match "${label}" on ${repo}; ` +
      `running against the most recent: #${issue.number} - ${issue.title}`
    )
  }
  const [repoOwner, repoName] = repo.split("/")
  return {
    initialState: {
      github_issue: {
        issue_number:   issue.number,
        title:          issue.title,
        body:           issue.body,
        url:            issue.url,
        author:         issue.author,
        labels:         issue.labels,
        label_added:    label,
        repo_full_name: repo,
        repo_name:      repoName,
        repo_owner:     repoOwner,
        default_branch: "main",
        clone_url:      issue.clone_url,
      },
      github_trigger: {
        event_type: "github_issue_labeled",
        label,
        repo: {
          full_name:      repo,
          name:           repoName,
          owner:          repoOwner,
          default_branch: "main",
          clone_url:      issue.clone_url,
        },
        issue: {
          number: issue.number,
          title:  issue.title,
          body:   issue.body,
          url:    issue.url,
          author: issue.author,
          labels: issue.labels,
        },
      },
    },
  }
}
