export type FederationAttribution = {
  caller_id: string; principal_id: string; grant_id: string; connection_id: string
  request_id: string; mapping_version: string; evidence_expires_at: string
}

export function AttributionDetails({ value }: { value: FederationAttribution }) {
  return <section aria-label="Recorded delegated identity" style={{ width: "100%", borderTop: "1px solid var(--border)", paddingTop: 12, overflowWrap: "anywhere" }}>
    <strong>Recorded delegated identity</strong>
    <dl style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 2fr)", gap: "6px 12px", marginTop: 8 }}>
      <dt>Calling integration</dt><dd style={{ margin: 0 }}><a href={`/agent-identity?tab=identities&id=${encodeURIComponent(value.caller_id)}`}>{value.caller_id}</a></dd>
      <dt>Acting principal</dt><dd style={{ margin: 0 }}>{value.principal_id}</dd>
      <dt>Delegation grant</dt><dd style={{ margin: 0 }}>{value.grant_id}</dd>
      <dt>Trust connection</dt><dd style={{ margin: 0 }}>{value.connection_id} (revision {value.mapping_version})</dd>
      <dt>Evidence expires</dt><dd style={{ margin: 0 }}>{new Date(value.evidence_expires_at).toLocaleString(undefined, { timeZoneName: "short" })}</dd>
      <dt>Verification request</dt><dd style={{ margin: 0 }}>{value.request_id}</dd>
    </dl>
    <p style={{ color: "var(--text-3)", marginBottom: 0 }}>Verified for this recorded request. Current authorization may differ.</p>
  </section>
}
