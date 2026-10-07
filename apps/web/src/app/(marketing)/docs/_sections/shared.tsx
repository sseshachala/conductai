// ── Shared components ──────────────────────────────────────────────────────────

export function Code({ children }: { children: React.ReactNode }) {
  return <code className="bg-stone-100 px-1.5 py-0.5 rounded text-sm font-mono text-stone-800">{children}</code>
}

export function Pre({ children }: { children: string }) {
  return (
    <pre className="bg-stone-900 text-stone-100 rounded-xl px-5 py-4 text-sm font-mono overflow-x-auto leading-relaxed">
      {children}
    </pre>
  )
}

export function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <li className="flex gap-3 mb-2">
      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-stone-900 text-white text-xs font-semibold grid place-items-center mt-0.5">{n}</span>
      <div className="flex-1 text-stone-700 leading-relaxed">{children}</div>
    </li>
  )
}

export function SectionHeading({ id, children }: { id: string; children: React.ReactNode }) {
  return <h2 id={id} className="text-xl font-bold text-stone-900 mb-1 scroll-mt-8">{children}</h2>
}

export function SubHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-sm font-semibold text-stone-700 mb-2 mt-5">{children}</h3>
}

export function Screenshot({ src, alt, caption }: { src: string; alt: string; caption: string }) {
  return (
    <figure className="my-4">
      <img src={src} alt={alt} className="rounded-xl border border-stone-200 w-full shadow-sm" />
      <figcaption className="text-xs text-stone-400 mt-2 text-center">{caption}</figcaption>
    </figure>
  )
}

function Method({ m }: { m: string }) {
  const colors: Record<string, string> = {
    GET:    "bg-blue-50 text-blue-700",
    POST:   "bg-green-50 text-green-700",
    DELETE: "bg-red-50 text-red-700",
    PATCH:  "bg-amber-50 text-amber-700",
  }
  return <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono ${colors[m] ?? "bg-stone-100 text-stone-600"}`}>{m}</span>
}

export function Endpoint({ method, path, desc, children }: { method: string; path: string; desc: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-stone-200 overflow-hidden mb-4">
      <div className="flex items-center gap-3 px-4 py-3 bg-stone-50 border-b border-stone-200">
        <Method m={method} />
        <code className="text-sm font-mono text-stone-800 font-medium">{path}</code>
      </div>
      <div className="px-4 py-3">
        <p className="text-sm text-stone-600 mb-3">{desc}</p>
        {children}
      </div>
    </div>
  )
}
