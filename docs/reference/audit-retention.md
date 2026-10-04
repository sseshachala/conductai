## Audit retention

The same worker supports SaaS and on-prem. Use AWS S3 or an S3-compatible HTTPS
endpoint. No raw cleanup runs by default.

Search embeddings expire after 30 days by default (`GUARD_PROJECTION_RETENTION_DAYS`).
The projection retention worker backfills legacy source timestamps and expiry,
then prunes expired embeddings in bounded batches. It preserves current rules and
discovered-agent documents. Enable `GUARD_PROJECTION_RETENTION_CLEANUP_ENABLED`
with `GUARD_PROJECTION_RETENTION_DRY_RUN=true` first; inspect the aggregate metrics.

### Configure archives

Set these on the API and worker. Helm uses `config.extraEnv` and the backend Secret.
Render operators use the API and worker Environment settings or a shared env group.

| Setting | Value |
| --- | --- |
| `GUARD_AUDIT_RETENTION_ENABLED` | `false` by default; `true` starts the worker daemon |
| `GUARD_AUDIT_RETENTION_DRY_RUN` | `true` by default; reports candidates without uploads or cleanup |
| `GUARD_AUDIT_RETENTION_DAYS` | Your compliance period; unset means no cleanup |
| `GUARD_AUDIT_RETENTION_BATCH_SIZE` | `100` events per workspace per pass; maximum `1000` |
| `GUARD_AUDIT_RETENTION_INTERVAL_SECONDS` | `3600` by default |
| `GUARD_AUDIT_ARCHIVE_BUCKET` | Your archive bucket |
| `GUARD_AUDIT_ARCHIVE_ENDPOINT` | Private S3-compatible HTTPS URL; omit for AWS S3 |
| `GUARD_AUDIT_ARCHIVE_REGION` | `us-east-1` by default |
| `GUARD_AUDIT_ARCHIVE_PREFIX` | `conduct/audit` by default |
| `GUARD_AUDIT_ARCHIVE_PATH_STYLE` | Set `true` if your storage requires path-style requests |
| `GUARD_AUDIT_ARCHIVE_CA_BUNDLE` | Optional complete corporate CA bundle mounted on both services |
| `GUARD_AUDIT_ARCHIVE_ACCESS_KEY_ID`, `GUARD_AUDIT_ARCHIVE_SECRET_ACCESS_KEY`, `GUARD_AUDIT_ARCHIVE_SESSION_TOKEN` | Storage credentials in Secrets; AWS credential-chain/IAM roles also work |
| `GUARD_AUDIT_ARCHIVE_SIGNING_KEY` | Dedicated random key with at least 32 characters |
| `GUARD_AUDIT_ARCHIVE_ENCRYPTION_KEY` | Different random key with at least 32 characters |
| `GUARD_AUDIT_ARCHIVE_TIMEOUT_SECONDS` | `10` seconds per connect/read, with two total attempts |
| `GUARD_AUDIT_ARCHIVE_MAX_BYTES` | `16 MiB` per uncompressed batch; reduce batch size if needed |

Set the audit compliance period to at least the search retention period so queued
projections never lose their source payload early. An enabled worker without a
compliance period reports a configuration error and performs no cleanup.

Storage must support conditional `PutObject` with `If-None-Match: *` and read-back.
Unsupported storage fails closed. Grant only Put/Get access under the deployment's
archive prefix. Use bucket versioning and Object Lock where required by your
compliance policy. Keep archives indefinitely unless an approved archive lifecycle
and legal-hold process are in place. Conduct does not delete archive objects.
Back up both archive keys; do not replace them while existing archives depend on them.

### Preview and apply

Run from the repository root using the API Python environment and configured
deployment variables:

```sh
python tools/audit_retention.py preview --workspace-id WORKSPACE_UUID
python tools/audit_retention.py apply --workspace-id WORKSPACE_UUID
python tools/audit_retention.py verify --workspace-id WORKSPACE_UUID
```

`apply` requires `GUARD_AUDIT_RETENTION_ENABLED=true`. The worker uses the dry-run
setting; keep it true until the preview is reviewed, then set it false to apply.
Each apply archives only one bounded prefix. Repeating it resumes from the next
unarchived event. Upload/read-back/manifest failure causes zero payload cleanup.
All storage I/O runs after owned database sessions close.

### What stays online

Full events are compressed, AES-GCM encrypted and stored with an HMAC-authenticated
manifest. Cleanup removes `input_summary`, `result_summary` and `blast_radius`
from the online event only after successful verification. Small event records,
receipt IDs and decisions, evaluated rules, routing/accounting metadata and hash-chain fields
remain online. IDs, links, usage, spend totals, reconciliation and foreign-key
references do not change. This is payload compaction, not audit-row deletion.

`GET /guard/audit-retention/events/EVENT_UUID` retrieves and verifies a full archived
event for users with `guard.settings.edit`. Existing receipt endpoints remain available;
their old input summaries are retrieved through the archive endpoint after compaction.
Chain endpoints authenticate each archived prefix checkpoint before checking the
retained tail. The operator `verify` command also reads and authenticates every
stored segment and manifest.

### Legal holds

Users with `guard.settings.edit` can manage holds using `POST /guard/audit-retention/holds`
with `starts_at`, optional `ends_at`, and `reason`. Timestamps include timezones.
List with `GET /guard/audit-retention/holds`; release with
`DELETE /guard/audit-retention/holds/HOLD_UUID`. Hold ranges include both endpoints.
An active hold, pending approval, open budget reservation or unfinished audit
lifecycle stops the prefix. No held gap is skipped. Holds/source changes during
upload are checked again in the cleanup transaction.
Holds do not restore already compacted payloads or replace storage-side legal holds.

### Monitor

Monitor `guard_audit_retention_runs_total`, `guard_audit_retention_events_total`
and `guard_audit_retention_last_success_timestamp_seconds`. Alert on failures or
missing scheduled successes. Logs contain aggregate counts and error types only.
Continue monitoring database size, projection backlog and pool checkout metrics.
Ordinary vacuum makes cleared payload space reusable; it does not guarantee an
immediate reduction in the database file size. Capacity mitigation remains separate.
