/**
 * Generate the canonical YAML filename for a workflow.
 *
 * Convention: `<projectname>-delegator.yml`
 *
 * The "projectname" portion is the workflow name slugified — lowercased,
 * whitespace and non-alphanumerics collapsed to hyphens, leading/trailing
 * hyphens trimmed. Falls back to "workflow" when the name is empty.
 *
 * Examples:
 *   "AI-Ready Autopilot"        -> "ai-ready-autopilot-delegator.yml"
 *   "Marshal"                   -> "marshal-delegator.yml"
 *   "  Deploy delegator   "     -> "deploy-delegator-delegator.yml"
 *   ""                          -> "workflow-delegator.yml"
 */
export function slugifyWorkflowName(name: string): string {
  const slug = name
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80)
  return slug || "workflow"
}

export function yamlFilenameFor(name: string): string {
  return `${slugifyWorkflowName(name)}-delegator.yml`
}
