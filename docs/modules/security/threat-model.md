# Security Threat Model

## Sandbox Credential Isolation {#sandbox-credentials}

When a playbook runs on a third-party compute provider — E2B, Modal, or an SSH host — Conduct never exposes your API keys or tokens to the internet, to its own API worker, or to other tenants on the platform.

### How credentials travel

You store provider keys once in **Settings → Environments** as plain `KEY=value` pairs. At run time, the following chain ensures the key never leaves your trust boundary until it is needed:

```
Settings → Environments
  └─ stored encrypted in Conduct's credential vault
       └─ decrypted in-memory when a run starts
            └─ passed to the session adapter as a dict
                 └─ injected into a subprocess environment (proc_env)
                      └─ subprocess calls the provider's API over TLS
```

The key exists in exactly one place at a time and is never written to disk, logged, or included in any HTTP response.

### Three guarantees

**1. Never on the inbound wire**

Your API key is not part of the HTTP request that triggers a run. It is retrieved from the vault server-side, so it never appears in request logs, load balancer access logs, or API gateway traces.

**2. Never in the main process environment**

Conduct's API worker process does not set your provider key in its own `os.environ`. Instead, the key is placed in a separate `env` dict and handed to a short-lived subprocess via `subprocess.Popen(..., env=proc_env)`. Other requests running concurrently in the same worker cannot read it.

**3. Lifetime-scoped to the run**

The subprocess that holds the key exits when the sandbox block completes. There is no lingering environment variable, no shared memory segment, and no cached credential object after the run ends.

### Isolation diagram

```
┌─────────────────────────────────────────┐
│  Conduct API worker process             │
│                                         │
│  proc_env = { "E2B_API_KEY": "sk-..." } │  ← in-memory dict only
│         │                               │
│         │  subprocess.Popen(env=...)    │
│         ▼                               │
│  ┌─────────────────────────────────┐   │
│  │  e2b_session_runner subprocess  │   │
│  │  os.environ["E2B_API_KEY"] ✓   │   │
│  │         │                       │   │
│  │         │  HTTPS (TLS) outbound │   │
│  │         ▼                       │   │
│  │    E2B / Modal / SSH API        │   │
│  └─────────────────────────────────┘   │
│  (subprocess exits → key gone)         │
└─────────────────────────────────────────┘
```

### What this prevents

| Threat | Mitigation |
|--------|------------|
| Key leaked in HTTP request logs | Key is vault-sourced, never in the request |
| Key exposed to concurrent requests | Worker `os.environ` is never modified |
| Key persists after run failure | Subprocess exit clears it unconditionally |
| Key visible to other tenants | Subprocess is per-run, not shared |
| Key intercepted in transit to provider | Outbound call is TLS-encrypted |

### Supported providers

| Provider | Credential used | Where it's set |
|----------|-----------------|----------------|
| E2B | `E2B_API_KEY` | Settings → Environments |
| Modal | `MODAL_TOKEN_ID` + `MODAL_TOKEN_SECRET` | Settings → Environments |
| SSH | Private key via integration handle | Settings → Integrations |
| Local | None (development only, blocked in production) | — |

Local sandboxes are explicitly blocked in production environments — if a playbook specifies `provider: local` and the platform is running in production mode, the run fails immediately with a clear error before any sandbox is created.

### Reporting a vulnerability

If you discover a security issue, email [security@conductai.ai](mailto:security@conductai.ai). We aim to respond within 24 hours and will coordinate disclosure with you.
