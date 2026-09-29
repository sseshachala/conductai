# Conduct — HPE Private Cloud AI Helm chart

Installs Conduct on **HPE Private Cloud AI** via the AI Essentials **Import
Framework** wizard. Also installs on any upstream Kubernetes ≥ 1.27 that has
Istio available (the Kyverno policy is optional).

## What ships

| Component | Kind | Replicas |
|---|---|---|
| `api` | Deployment | 1 |
| `gateway` | Deployment | 1 |
| `worker` | Deployment | 1 |
| `web` | Deployment | 1 |
| `postgres` | StatefulSet | 1 (pgvector/pgvector:pg16, 20 Gi PVC) |
| `redis` | StatefulSet | 1 (redis:7-alpine, 5 Gi PVC, `noeviction`) |
| PCAI ingress | Istio `VirtualService` | 1 |
| PCAI labels | Kyverno `ClusterPolicy` | 1 (optional) |

**Fresh install footprint:** 6 pods, ~1.2 CPU / 2 Gi requests, ~25 Gi PVCs.

## Install on PCAI (Import Framework)

1. Package the chart:
   ```
   helm package deploy/helm/conduct
   ```
2. In AI Essentials → **Import Framework**, upload `conduct-0.1.0.tgz`.
3. On the values screen, at minimum override:
   - `ezua.endpoint` — public hostname (defaults to `conduct.${DOMAIN_NAME}`).
   - `secrets.values.anthropicApiKey`, `secrets.values.encryptionKey`,
     `secrets.values.postgresPassword` — required.
   - `image.api.repository`, `image.web.repository` — swap for your Harbor
     registry paths if the cluster is air-gapped. See
     [Harbor as a local registry on PCAI](https://developer.hpe.com/blog/setting-up-harbor-as-a-local-container-registry-in-hpe-private-cloud-ai/).
   - `image.pullSecrets` — `[{name: harbor-creds}]` for air-gapped pulls.
   - `postgres.storage.storageClass`, `redis.storage.storageClass` — set to
     the Ezmeral CSI storage class name if the cluster default isn't right.
4. Apply. First install takes ~3 minutes (Postgres init + Alembic migrations).

## Install on plain Kubernetes

```
helm upgrade --install conduct deploy/helm/conduct \
  --namespace conduct --create-namespace \
  --set secrets.values.anthropicApiKey=sk-ant-… \
  --set secrets.values.encryptionKey=$(openssl rand -hex 16) \
  --set secrets.values.postgresPassword=$(openssl rand -hex 16) \
  --set kyvernoLabelPolicy.enabled=false
```

Skip Istio-flavored ingress if you're not on PCAI: leave the VirtualService
in place but point your own ingress (nginx, Traefik) at the `conduct-web`
and `conduct-api` Services directly.

## Values reference

See `values.yaml` — every knob is commented in place.

## Known limitations (track 1 scope)

- **`api.replicas` > 1 races migrations.** The API pod runs
  `alembic upgrade head` on start (matches the Dockerfile prod stage). Two
  pods restarting together during `helm upgrade` will race the same
  migration. Fix path: override the api container command to `uvicorn …`
  only and add a `helm.sh/hook: pre-upgrade` migration Job. Deferred until
  a customer asks for HA.
- **Web image bakes `NEXT_PUBLIC_API_URL` at build time.** The chart works
  around this by using the Istio VirtualService to rewrite same-origin
  `/api/*` requests to the API Service. If a customer wants a different
  API hostname, the web image has to be rebuilt.
- **No PDB / HPA / ServiceMonitor.** No metrics scraping, no autoscaling,
  no pod disruption budgets. Add when the operator asks.
- **Postgres and Redis are single-replica.** Fine for a proof-of-concept
  and matches the Render production topology today. For HA, plug in an
  operator-managed Postgres/Redis and set `secrets.existingSecret` with a
  `DATABASE_URL` / `REDIS_URL` pointing at it. (The chart's Postgres and
  Redis StatefulSets can be disabled with a small future values gate; not
  wired yet — YAGNI.)
- **Secrets in `values.values.*` land in the release manifest.** OK for a
  trial. For production, always use `secrets.existingSecret` with a Secret
  you manage out-of-band (Sealed Secrets, ESO, Vault CSI, etc.).

## Uninstall

```
helm uninstall conduct -n conduct
kubectl delete pvc -n conduct -l app.kubernetes.io/instance=conduct   # nukes data
```
