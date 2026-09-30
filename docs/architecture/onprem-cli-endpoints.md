# CLI Deployment Endpoints

Console identity and CLI deployment routing are separate concerns. Clerk and
proxy/OIDC deployments use the same CLI commands after login. The CLI persists
the selected deployment in `~/.conduct/config.json`; subsequent commands and
hooks read that configuration.

```sh
conduct login --server https://api.example.internal \
  --web-url https://console.example.internal \
  --gateway-url https://llm.example.internal/gateway/v1 \
  --mcp-url https://api.example.internal/mcp
conduct guard sync
```

- `--server` is the API origin. `--web-url` is the browser console origin and is
  required for browser login to a new custom deployment.
- `--gateway-url` is optional for policy-only deployments. It includes the
  Gateway base path, normally `/gateway/v1`.
- `--mcp-url` is optional; the default is the selected API origin plus `/mcp`.
- `--no-sync` on login saves credentials without installing hooks or tool routing.
- Switching API origins clears the old workspace and refresh credentials. Use
  separate OS homes for independent test and production configurations.

Custom deployments never default to Conduct's hosted console or Gateway.
Guard sync can discover a custom Gateway from the selected API's proxy metadata.
If it cannot, a fresh policy-only setup skips inference routing. If managed
routing files already exist, sync stops and asks for an explicit Gateway instead
of silently retaining old routing. `conduct guard sync --proxy-url URL` overrides
and persists the Gateway selection. A stale `CONDUCT_PROXY_URL` targeting Conduct
SaaS is rejected for custom deployments.

Sync writes the selected Gateway into POSIX/PowerShell environment files and
Codex provider configuration, and the selected MCP endpoint into tool settings.
Existing native OAuth registrations are not reused across different MCP URLs;
users must authenticate again. Restart tools and source the generated environment
after switching deployments. User-managed `env-override` files and already-running
process environments remain the user's responsibility.

Automatic CLI/package upgrades and Booster auto-installation are skipped for
custom deployments. Error reporting uses the saved API, not a hosted fallback.
For air-gapped installations, provision dependencies and the `mcp-remote` bridge
offline; its generated `npx` invocation can otherwise attempt a registry download.
This routing support is not itself proof of fully air-gapped operation.

For the local console acceptance stack, use API `https://localhost:3444` and web
`https://localhost:3443`, an isolated `HOME`, and `SSL_CERT_FILE` pointing to the
trusted test CA. Do not disable TLS verification. Omit Gateway configuration when
testing only console login and API authorization.
