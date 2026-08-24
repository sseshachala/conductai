# Conduct Guard + Proliferate — drop-in files

Concrete diffs to add Conduct Guard to a Proliferate self-host. Assumes
you've cloned [`proliferate-ai/proliferate`](https://github.com/proliferate-ai/proliferate)
alongside this repo.

## Files in this directory

- `Dockerfile.with-conduct` — a 2-line Dockerfile that layers
  `conduct-litellm-guard` onto Proliferate's LiteLLM image. Drop into
  `proliferate/server/litellm/Dockerfile.with-conduct`.
- `docker-compose.override.yml` — Compose override that swaps
  Proliferate's vanilla LiteLLM image for the layered one and adds
  `CONDUCT_AGENT_TOKEN` to the environment. Drop into
  `proliferate/server/docker-compose.override.yml`.
- `config.patch.yaml` — the `guardrails:` block to append to
  Proliferate's `server/litellm/config.yaml`, right before or after
  `general_settings:`.

## Wire-up

```bash
# 1. Copy fixtures into your Proliferate checkout.
cp Dockerfile.with-conduct         /path/to/proliferate/server/litellm/
cp docker-compose.override.yml     /path/to/proliferate/server/
# 2. Manually append config.patch.yaml contents to
#    /path/to/proliferate/server/litellm/config.yaml
# 3. Export the token.
export CONDUCT_AGENT_TOKEN=cond_agt_...
# 4. Start the stack.
cd /path/to/proliferate/server && docker compose up -d litellm
```

Docker Compose auto-detects `docker-compose.override.yml` and merges
it with `docker-compose.yml` — no flag needed.

## Verify

```bash
# Send a request through Proliferate's LiteLLM proxy (port 14000).
curl -X POST http://localhost:14000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-proliferate-local-dev" \
  -d '{
    "model": "claude-haiku-4-5",
    "messages": [{"role": "user", "content": "Hello"}],
    "guardrails": ["conduct-guard"]
  }'
```

Check the Conduct console at `/theguard/activity` — the request should
appear with `TOOL: litellm`, `CALL: workflow`, `DECISION: Audited`
(or `Allowed` if no rule matched).

## Production deployment (ECS)

Proliferate's production LiteLLM image is built from
`server/litellm/Dockerfile`. Add one line to that file to bake
`conduct-litellm-guard` into the deployed image:

```diff
 FROM ghcr.io/berriai/litellm:v1.93.0@sha256:...

+RUN pip install --no-cache-dir conduct-litellm-guard
 COPY server/litellm/config.yaml /app/proliferate-litellm-config.yaml
```

The config file edit from `config.patch.yaml` applies to both dev and
prod — one YAML block covers both paths.
