# Discovery Evidence

## Scope

`conduct guard discover` and `conduct guard watch` share one collector.
The collector identifies Claude Code, Codex, Cursor, Windsurf and Copilot CLI
from installation/configuration locations and exact executable names.
Current-directory dependency manifests can identify possible LangChain, CrewAI,
AutoGen, OpenAI Agents and LlamaIndex integrations. A dependency is not a running
agent. Generic Python processes, updater processes and command-line substrings
are not agent identities.

No secret-file scanning, command arguments, hostnames or local paths are included
in discovery payloads. Structured tool configuration is inspected locally and
reduced to allowlisted facts. Existing hook event reporting is unchanged except
for two discovery identity fields.

## Identity And Evidence

- A random device ID is persisted in `~/.conduct/discovery-device-id`.
- Installation identity hashes the canonical tool and resolved configuration
  root. The API keys findings by workspace, device and installation.
- Project integrations use the manifest directory as their local identity root.
- Installed, running-at-scan and possible-integration findings are distinct.
- Hook configuration is not observed activity. Only event ingestion can attach
  a hook receipt and observation timestamp; scans cannot set them.
- Hook observations are client-reported evidence, not remote attestation or proof
  of continuous enforcement. Gateway configuration does not prove inference
  traffic. This release does not infer Gateway activity from a base URL.
- Evidence is recent for 24 hours. A new scan does not refresh old hook evidence.
  Missing findings are retained, not declared removed by a partial scan.
- Legacy findings remain unverified, with no inferred risk or coverage score.
  They cannot safely be assigned to a particular device during migration.

## Surfaces

The CLI scan result, API, MCP and Lens use the same server evidence projection.
The CLI prints local-only status when upload fails. Watch records partial/failed
scans when possible and reports upload failures instead of silently exiting.

Discovery shows installations, possible integrations, recent hook activity and
findings needing review. The searchable, paginated table exposes device identity,
configuration and freshness. Evidence opens in a side panel with safe signals,
UTC timestamps, copyable setup commands, and a Flight Recorder / Ask Lens link
when an observation exists. Registering a row cannot mark it protected.

## Deployment

1. Apply migration `0153` before deploying the API. It adds identity/observation
   columns and an installation unique key. The original legacy unique key remains
   valid for old API writers during a rolling deployment. Normalized rows use a
   NULL database source to avoid collapsing installations under that legacy key;
   readers project their source as `inventory`.
2. The migration clears legacy unstructured evidence/location and protection
   flags and removes cached discovery knowledge entries. New readers never trust
   legacy flags, including flags rewritten by an old API during rollout.
3. Deploy API and web, then release the CLI. Existing CLIs can still upload
   legacy scans, but cannot provide installation-linked evidence.
4. On each device, upgrade, run `conduct guard discover`, and exercise a supported
   hooked tool. Refresh Discovery to check the linked observation. `conduct guard
   sync` remains the supported setup command; restart the tool after syncing.

The migration permits downgrade before installation evidence has been written,
including the CI up/down cycle. It locks the table and checks all new columns
before dropping them. Once evidence exists, downgrade is refused to avoid losing
attribution. Roll back application code without downgrading this additive schema,
or prepare an explicit data-preserving plan. Cleared legacy unsafe evidence and
cached knowledge entries are not restored by downgrade.

## Verification

- CLI: `python -m pytest packages/conduct-cli/tests/test_discovery_inventory.py`
- API: `python -m pytest tests/test_discovery_evidence.py`
- PostgreSQL: set `DISCOVERY_TEST_DATABASE_URL` to a disposable database and run
  `python -m pytest tests/test_discovery_evidence_postgres.py`. Each test creates
  and drops only its own randomly named schema. Also runs in API CI.
- Web: `npx vitest run 'src/app/(app)/theguard/discovery/page.test.tsx'`.
- Manually check desktop/mobile layout, keyboard dismissal/focus restoration,
  evidence links and clipboard behavior after deployment.

Remote/container/GitHub scanners and native Linux/Windows validation of this
change are not claimed by the local test results.
