# Load tests

k6 scripts for baseline performance + regression detection.

## Local run

```bash
# Install k6 (macOS)
brew install k6

# Point at a running API (local dev, default loopback)
export CONDUCT_API_URL=$(printf 'http:%s' '//127.0.0.1:8000')

# Baseline: unauthenticated /health at 50 rps for 30s
k6 run load/health-baseline.js
```

## CI

The `load-baseline.yml` workflow runs on `workflow_dispatch` (manual) and
weekly cron. Results archived as artifacts; regression alerting comes when
we wire the first pass through k6 cloud or self-hosted output.

## Files

- `health-baseline.js` — steady-state read baseline against `/health`. Cheap,
  proves the pipeline works. Grow into per-endpoint scenarios once green.
