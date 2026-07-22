export interface Instructions {
  content: string
  version: string
  updated_at: string
  updated_by: string
}

export interface AdoptionRow {
  email: string
  tools: string[]
  last_synced: string | null
  version: string | null
}

export const MOCK_INSTRUCTIONS: Instructions = {
  content: "",
  version: "v1",
  updated_at: new Date().toISOString(),
  updated_by: "admin",
}

export const MOCK_ADOPTION: AdoptionRow[] = [
  { email: "sudhi@b2bsphere.com", tools: ["claude-code", "copilot"], last_synced: new Date().toISOString(), version: "v1" },
  { email: "alice@example.com",   tools: ["cursor"], last_synced: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(), version: "v0" },
  { email: "bob@example.com",     tools: [], last_synced: null, version: null },
]
