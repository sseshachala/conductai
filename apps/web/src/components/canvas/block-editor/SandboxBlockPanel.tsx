"use client"

// ── Sandbox block config panel ────────────────────────────────────────────────

export function SandboxBlockPanel({ blockData, blockId, onChange, isViewer, sectionLabel, section, inputBase }: {
  blockData: Record<string, unknown>
  blockId: string
  onChange: (id: string, data: Record<string, unknown>) => void
  isViewer: boolean
  sectionLabel: string
  section: string
  inputBase: string
}) {
  const config = (blockData.sandbox_config as Record<string, unknown>) || {}

  function updateConfig(patch: Record<string, unknown>) {
    onChange(blockId, { ...blockData, sandbox_config: { ...config, ...patch } })
  }

  const setupText = Array.isArray(config.setup) ? (config.setup as string[]).join("\n") : (config.setup as string) || ""

  return (
    <>
      {/* Provider */}
      <div className={section}>
        <span className={sectionLabel}>Provider</span>
        <select
          value={(config.provider as string) || ""}
          onChange={e => updateConfig({ provider: e.target.value || undefined })}
          className={inputBase}
          disabled={isViewer}
        >
          <option value="">Select provider…</option>
          <option value="e2b">E2B — isolated microVM</option>
          <option value="modal">Modal Labs — serverless GPU / CPU</option>
        </select>
        <p className="text-[10px] text-stone-400 mt-1 leading-relaxed">
          {config.provider === "e2b" && "Needs E2B_API_KEY in your environment credentials."}
          {config.provider === "modal" && "Needs MODAL_TOKEN_ID + MODAL_TOKEN_SECRET in credentials."}
          {!config.provider && "Choose where to provision the shared compute environment."}
        </p>
      </div>

      {/* Setup commands */}
      <div className={section}>
        <span className={sectionLabel}>Setup commands</span>
        <textarea
          rows={6}
          value={setupText}
          onChange={e => {
            const lines = e.target.value.split("\n").filter(l => l.trim())
            updateConfig({ setup: lines })
          }}
          placeholder={"git clone https://github.com/org/repo.git /workspace\ncd /workspace && npm install"}
          className={`${inputBase} resize-none font-mono text-[11px]`}
          disabled={isViewer}
        />
        <p className="text-[10px] text-stone-400 mt-1">
          One command per line. Runs in order when the sandbox provisions. Failure stops the run.
        </p>
      </div>
    </>
  )
}
