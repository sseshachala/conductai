// Shared policy templates used by the NLP new-policy page and the quick-add modal.

export interface PolicyTemplate {
  label: string
  prompt: string
}

export const POLICY_TEMPLATES: PolicyTemplate[] = [
  { label: "Approve merge to main",      prompt: "Require approval before merging to the main or master branch" },
  { label: "Meaningful commit messages", prompt: "Warn when commit messages are shorter than 10 characters or left empty" },
  { label: "No PII in files",            prompt: "Block writing files that contain email addresses or phone numbers" },
  { label: "No SELECT *",               prompt: "Warn when SQL queries use SELECT * instead of explicit column names" },
  { label: "No hardcoded IPs",           prompt: "Block hardcoded IP addresses in source code files" },
  { label: "Audit dependency changes",   prompt: "Audit any changes to package.json, requirements.txt, or pyproject.toml" },
  { label: "Non-standard registries",    prompt: "Warn when installing packages from non-standard or private registries" },
  { label: "No privileged ports",        prompt: "Block opening or binding to ports below 1024 in code" },
  { label: "Approve K8s manifests",      prompt: "Require approval before modifying Kubernetes manifest files" },
  { label: "Audit Terraform state",      prompt: "Audit any changes to Terraform state files (.tfstate)" },
]
