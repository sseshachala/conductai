# Self-Hosted Dev Infrastructure Spec
**Version 1.0 | June 2026**

---

## Goal

Replace Vercel + Render with a single VM running Docker Compose.
Every git push triggers a rebuild and redeploy automatically.
Target cost: ~$50/mo vs $220/mo current.

---

## Architecture

```
VM (8 vCPU, 16GB RAM — Hetzner CX41 or OVH Rise-1)
├── Caddy          — reverse proxy + automatic HTTPS (Let's Encrypt)
├── apps/web       — Next.js container
├── apps/api       — FastAPI container
├── postgres       — primary database
├── redis          — queue + cache
└── Watchtower     — auto-pull + restart on new image push
```

**Deploy flow:**
1. Push to `main`
2. GitHub Actions builds Docker images → pushes to GHCR (free)
3. Watchtower on VM detects new image → pulls → restarts container
4. Zero manual deploys

---

## VM Recommendation

| Provider | Machine | vCPU | RAM | Price |
|---|---|---|---|---|
| Hetzner | CX41 | 4 vCPU | 16GB | ~$18/mo |
| Hetzner | CX51 | 8 vCPU | 32GB | ~$35/mo |
| OVH | Rise-1 | 4 vCPU | 32GB | ~$40/mo |
| Hetzner | dedicated | 8 vCPU | 64GB | ~$55/mo |

Start with CX41. Upgrade if needed.

---

## docker-compose.yml

```yaml
version: "3.9"

services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config

  web:
    image: ghcr.io/sseshachala/conductai-web:latest
    restart: unless-stopped
    environment:
      - NEXT_PUBLIC_API_URL=https://api.conductai.dev
    depends_on:
      - api

  api:
    image: ghcr.io/sseshachala/conductai-api:latest
    restart: unless-stopped
    env_file: .env
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: conduct
      POSTGRES_USER: conduct
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

  watchtower:
    image: containrrr/watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - WATCHTOWER_POLL_INTERVAL=60
      - WATCHTOWER_CLEANUP=true
      - WATCHTOWER_INCLUDE_RESTARTING=true
    command: web api

volumes:
  caddy_data:
  caddy_config:
  postgres_data:
  redis_data:
```

---

## Caddyfile

```
conductai.dev {
    reverse_proxy web:3000
}

api.conductai.dev {
    reverse_proxy api:8000
}
```

---

## GitHub Actions — Build + Push

`.github/workflows/deploy.yml`:

```yaml
name: Build and Deploy

on:
  push:
    branches: [main]

jobs:
  build-web:
    runs-on: ubuntu-latest
    if: contains(github.event.commits[0].modified, 'apps/web') || contains(github.event.commits[0].added, 'apps/web')
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          context: ./apps/web
          push: true
          tags: ghcr.io/sseshachala/conductai-web:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

  build-api:
    runs-on: ubuntu-latest
    if: contains(github.event.commits[0].modified, 'apps/api') || contains(github.event.commits[0].added, 'apps/api')
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          context: ./apps/api
          push: true
          tags: ghcr.io/sseshachala/conductai-api:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

---

## Security Hardening Checklist

### Firewall (UFW)
```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH — change to non-default port after setup
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

### SSH
```bash
# /etc/ssh/sshd_config
PasswordAuthentication no
PermitRootLogin no
Port 2222           # non-default port
```

### Fail2ban
```bash
apt install fail2ban
# default config protects SSH automatically
```

### Docker
- No root containers — add `USER` directive in all Dockerfiles
- Secrets via `.env` file, never baked into images
- GHCR images are private by default

---

## Migration Plan

| Step | Action |
|---|---|
| 1 | Provision VM, run hardening checklist |
| 2 | Write Dockerfiles for `apps/web` and `apps/api` |
| 3 | Test `docker-compose up` locally |
| 4 | Push to GHCR, verify Watchtower pulls |
| 5 | Point `conductai.dev` DNS to VM |
| 6 | Verify HTTPS via Caddy |
| 7 | Disable Render (API) |
| 8 | Keep Vercel for `conductai.ai` production frontend only |

---

## What to Keep on Vercel

`conductai.ai` (production marketing + console) stays on Vercel — edge CDN,
preview deployments for design reviews, zero ops overhead for the public-facing site.

Self-hosted VM = dev + staging + API. Vercel = production frontend only.

---

## Cost Comparison

| Current | Self-hosted |
|---|---|
| Vercel Pro: $220/mo | Hetzner CX41: $18/mo |
| Render: ~$25/mo | GitHub Actions: free |
| **Total: ~$245/mo** | **Total: ~$18/mo** |
