"use client"

import { PACK_CATALOG } from "./catalog"
import { CedarImportBanner, CedarExportBanner, CedarPackDownload } from "./CedarBanners"

// Skill Packs tab
export function SkillPacksTab({
  getToken, packCatalog, installedPacks, packInstalling, installPack, uninstallPack,
}: {
  getToken: (() => Promise<string | null>) | null
  packCatalog: typeof PACK_CATALOG
  installedPacks: Set<string>
  packInstalling: string | null
  installPack: (packId: string) => Promise<void>
  uninstallPack: (packId: string) => Promise<void>
}) {
  return (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <CedarImportBanner getToken={getToken} />
            <CedarExportBanner />
            {packCatalog.map(pack => {
              const installed = installedPacks.has(pack.id)
              const busy = packInstalling === pack.id
              return (
                <div key={pack.id} className="card" style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
                  {/* Header row, mirrors ModulesManager exactly */}
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                      <span style={{ width: 40, height: 40, borderRadius: 10, background: "var(--accent-weak)", color: "var(--accent-text)", display: "grid", placeItems: "center", flexShrink: 0, fontSize: 20 }} aria-hidden="true">
                        {pack.icon}
                      </span>
                      <div>
                        <h3 style={{ fontSize: 15, fontWeight: 650, color: "var(--text)", margin: 0 }}>
                          <a href={`/packs/${pack.id}`} style={{ color: "inherit", textDecoration: "none" }}>{pack.name}</a>
                        </h3>
                        <p style={{ fontSize: 12.5, color: "var(--text-3)", margin: "3px 0 0" }}>{pack.subtitle}</p>
                        <a href={`/packs/${pack.id}`} style={{ display: "inline-block", marginTop: 4, fontSize: 11, color: "var(--accent-text)" }}>View rules →</a>
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                      {installed && <span className="sbadge ok">✓ Installed</span>}
                      <CedarPackDownload slug={pack.id} getToken={getToken} />
                      {installed ? (
                        <>
                          <button onClick={() => installPack(pack.id)} disabled={!!packInstalling} className="btn btn-primary btn-sm" style={{ opacity: packInstalling && !busy ? 0.5 : 1 }}>
                            {busy ? "…" : "Reinstall"}
                          </button>
                          {pack.id === "conduct-base" ? (
                            <span title="Required — cannot be uninstalled" style={{ fontSize: 11, color: "var(--text-3)", display: "flex", alignItems: "center", gap: 3 }}>🔒 Required</span>
                          ) : (
                            <button onClick={() => uninstallPack(pack.id)} disabled={!!busy} className="btn btn-ghost btn-sm" style={{ color: "var(--err)" }}>
                              {busy ? "…" : "Uninstall"}
                            </button>
                          )}
                        </>
                      ) : (
                        <button onClick={() => installPack(pack.id)} disabled={!!packInstalling} className="btn btn-primary btn-sm" style={{ opacity: packInstalling && !busy ? 0.5 : 1 }}>
                          {busy ? "Installing…" : "Install"}
                        </button>
                      )}
                    </div>
                  </div>
                  {/* Rule count pills */}
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {"proxyRules" in pack ? (
                      <>
                        <span style={{ fontSize: 11, color: "var(--text-muted)", background: "var(--surface-3)", padding: "2px 8px", borderRadius: 20 }}>{pack.proxyRules} proxy</span>
                        <span style={{ fontSize: 11, color: "var(--text-muted)", background: "var(--surface-3)", padding: "2px 8px", borderRadius: 20 }}>{pack.agentRules} agent</span>
                        <span style={{ fontSize: 11, color: "var(--text-muted)", background: "var(--surface-3)", padding: "2px 8px", borderRadius: 20 }}>{pack.surfaceRules} surface</span>
                      </>
                    ) : (
                      <>
                        <span style={{ fontSize: 11, color: "var(--text-muted)", background: "var(--surface-3)", padding: "2px 8px", borderRadius: 20 }}>
                          {pack.guardRules} Guard {pack.guardRules === 1 ? "rule" : "rules"}
                        </span>
                        <span style={{ fontSize: 11, color: "var(--text-muted)", background: "var(--surface-3)", padding: "2px 8px", borderRadius: 20 }}>
                          {pack.securityRules} Security {pack.securityRules === 1 ? "rule" : "rules"}
                        </span>
                      </>
                    )}
                    {pack.tags.map(t => (
                      <span key={t} style={{ fontSize: 11, color: "var(--text-muted)", background: "var(--surface-3)", padding: "2px 8px", borderRadius: 20 }}>{t}</span>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
  )
}
