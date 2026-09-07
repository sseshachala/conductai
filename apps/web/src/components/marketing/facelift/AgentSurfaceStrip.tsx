"use client"

/**
 * AgentSurfaceStrip — canonical surface strip per plan §2.
 * Renders AGENT TOOLS / CLIENTS / BYO GATEWAYS blocks.
 */

export interface AgentSurfaceStripProps {
  imageSrc?: string
  imageAlt?: string
}

export function AgentSurfaceStrip({ imageSrc, imageAlt }: AgentSurfaceStripProps = {}) {
  if (imageSrc) {
    return (
      <img
        src={imageSrc}
        alt={imageAlt ?? "Agent surface strip"}
        loading="lazy"
        className="border border-stone-200 rounded-2xl shadow-sm w-full h-auto"
      />
    )
  }

  return (
    <div className="border border-stone-200 rounded-2xl overflow-hidden bg-white shadow-md text-sm">
      <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-stone-200">
        <SurfaceBlock
          label="AGENT TOOLS"
          items={[
            { name: "Claude Code", status: "shipped" },
            { name: "Cursor", status: "shipped" },
            { name: "Copilot", status: "shipped" },
            { name: "Codex", status: "shipped" },
          ]}
        />
        <SurfaceBlock
          label="CLIENTS"
          items={[
            { name: "Claude Desktop", note: "MCP", status: "shipped" },
            { name: "ChatGPT", note: "MCP", status: "shipped" },
            { name: "Cursor", note: "MCP", status: "shipped" },
            { name: "Custom agents", note: "proxy / MCP", status: "shipped" },
          ]}
        />
        <SurfaceBlock
          label="BYO GATEWAYS"
          items={[
            { name: "Azure OpenAI", status: "shipped" },
            { name: "OpenRouter", status: "shipped" },
            { name: "Portkey", status: "shipped" },
            { name: "Helicone", status: "shipped" },
            { name: "LiteLLM", status: "preview" },
            { name: "ConductAI native", status: "shipped" },
          ]}
        />
      </div>
    </div>
  )
}

type ItemStatus = "shipped" | "preview" | "planned"

function SurfaceBlock({
  label,
  items,
}: {
  label: string
  items: Array<{ name: string; note?: string; status: ItemStatus }>
}) {
  return (
    <div className="px-5 py-4">
      <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-stone-400 mb-3">{label}</p>
      <ul className="space-y-2.5">
        {items.map((item) => (
          <li key={item.name} className="flex items-center gap-2">
            <span className="text-[13px] text-stone-800 font-medium leading-snug">{item.name}</span>
            {item.note && (
              <span className="text-[10px] font-mono text-stone-500 bg-stone-50 border border-stone-200 rounded px-1.5 py-0.5 tracking-wide">
                {item.note}
              </span>
            )}
            {item.status === "preview" && (
              <span className="text-[10px] font-mono text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5 ml-auto tracking-wide uppercase">
                Preview
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
