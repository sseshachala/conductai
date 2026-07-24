"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"

export interface TokenGuardrails {
  prompt_caching: boolean
  model_routing: boolean
  prompt_splitting: boolean
  deterministic_offload: boolean
  output_compression: boolean
  structured_retrieval: boolean
  metrics_budgets: boolean
  manual_keys: string[]
  slack_webhook_url: string | null
  slack_integration_id: string | null
}

const DEFAULTS: TokenGuardrails = {
  prompt_caching: true,
  model_routing: true,
  prompt_splitting: true,
  deterministic_offload: true,
  output_compression: true,
  structured_retrieval: true,
  metrics_budgets: true,
  manual_keys: ["prompt_caching", "model_routing", "prompt_splitting"],
  slack_webhook_url: null,
  slack_integration_id: null,
}

interface UseTokenGuardrailsResult {
  guardrails: TokenGuardrails | null
  loading: boolean
  refresh: () => void
}

export function useTokenGuardrails(workspaceId: string | null): UseTokenGuardrailsResult {
  const { authFetch } = useAuthFetch()
  const [guardrails, setGuardrails] = useState<TokenGuardrails | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const data = await guard.tokenGuardrails.get(authFetch, workspaceId)
      setGuardrails(data)
    } catch {
      setGuardrails(DEFAULTS)
    } finally {
      setLoading(false)
    }
  }, [authFetch, workspaceId])

  useEffect(() => {
    setGuardrails(null)
    load()
  }, [load])

  return { guardrails, loading, refresh: load }
}

// Kept for callers that already hold a raw token + apiUrl (settings page patch flow).
export async function patchTokenGuardrails(
  workspaceId: string,
  token: string,
  apiUrl: string,
  patch: Partial<Pick<TokenGuardrails, "prompt_caching" | "model_routing" | "prompt_splitting">> & {
    slack_webhook_url?: string | null
    slack_integration_id?: string | null
  },
): Promise<TokenGuardrails> {
  const res = await fetch(`${apiUrl}/guard/token-guardrails?workspace_id=${workspaceId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ workspace_id: workspaceId, ...patch }),
  })
  if (!res.ok) throw new Error(`Save failed (${res.status})`)
  return res.json()
}
