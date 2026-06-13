"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"

export interface SchemaField {
  key: string
  label: string
  type: string
  required?: boolean
  readOnly?: boolean
  placeholder?: string
  hint?: string
  options?: { value: string; label: string }[]
  default?: string | boolean | number
}

export interface BlockSchemaDef {
  label: string
  icon?: string
  fields: SchemaField[]
  subtypes?: Record<string, { label: string; fields: SchemaField[] }>
}

export type BlockSchemaMap = Record<string, BlockSchemaDef>

let _cache: BlockSchemaMap | null = null

export function useBlockSchemas(): { schemas: BlockSchemaMap | null; loading: boolean } {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const { activeWorkspace } = useWorkspace()

  const [schemas, setSchemas] = useState<BlockSchemaMap | null>(_cache)
  const [loading, setLoading] = useState(_cache === null)

  useEffect(() => {
    if (_cache) return
    if (!isLoaded || !isSignedIn || !activeWorkspace?.id) return
    let cancelled = false

    async function fetch_() {
      try {
        const token = await getToken()
        if (!token) { if (!cancelled) setLoading(false); return }
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/meta/block-schemas?workspace_id=${activeWorkspace!.id}`,
          { headers: { Authorization: `Bearer ${token}` } }
        )
        if (res.ok) {
          const data: BlockSchemaMap = await res.json()
          _cache = data
          if (!cancelled) setSchemas(data)
        }
      } catch {
        // degrade gracefully — canvas still works with static config
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetch_()
    return () => { cancelled = true }
  }, [isLoaded, isSignedIn, activeWorkspace?.id, getToken])

  return { schemas, loading }
}

/** Return required field keys (canvas dot-paths) for a block type + optional subtype. */
export function getSchemaRequiredKeys(
  schemas: BlockSchemaMap | null,
  blockType: string,
  eventType?: string,
): string[] {
  if (!schemas) return []
  const def = schemas[blockType]
  if (!def) return []

  const topLevel = def.fields.filter(f => f.required).map(f => f.key)

  if (blockType === "trigger" && eventType && def.subtypes?.[eventType]) {
    const sub = def.subtypes[eventType].fields.filter(f => f.required).map(f => f.key)
    return [...topLevel, ...sub]
  }

  return topLevel
}
