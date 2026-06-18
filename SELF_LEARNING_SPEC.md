# Conduct — Self-Learning System Spec

Inspired by RuVector's self-improving vector DB concept, applied to Conduct's playbook runtime.
All features use data already collected — no new instrumentation needed for Features 1–3.

---

## Feature 1: Adaptive Turn Budgets

**What**: Surface per-playbook turn efficiency warnings. If a block consistently burns through its
budget and fails, Conduct proactively recommends a higher `max_turns`.

**Data source**: `runs.actual_turns`, `runs.budget_exhausted`, `runs.status`, `runs.max_turns`,
`run_analytics_events.playbook_slug`

### New table: `playbook_turn_stats`

```sql
CREATE TABLE playbook_turn_stats (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    playbook_slug   TEXT NOT NULL,
    workspace_id    UUID NOT NULL,
    window_days     INTEGER NOT NULL DEFAULT 30,
    sample_count    INTEGER NOT NULL,         -- # runs in window
    p50_turns       FLOAT,
    p75_turns       FLOAT,
    p95_turns       FLOAT,
    exhaustion_rate FLOAT,                    -- % of runs that hit budget_exhausted
    avg_max_turns   FLOAT,                    -- avg configured budget
    recommended_max INTEGER,                  -- p95 * 1.25, rounded to nearest 5
    computed_at     TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE (playbook_slug, workspace_id)
);
```

### Computation logic (runs as a nightly job)

```python
# Pseudo-code — runs nightly via existing APScheduler
for (slug, ws) in distinct (playbook_slug, workspace_id) from run_analytics_events:
    rows = runs WHERE playbook_slug = slug AND workspace_id = ws
               AND created_at > now() - 30d AND status IN ('succeeded', 'failed')
    p50, p75, p95 = percentile(rows.actual_turns, [50, 75, 95])
    exhaustion_rate = count(rows WHERE budget_exhausted=True) / count(rows)
    recommended_max = ceil(p95 * 1.25 / 5) * 5   # round up to nearest 5
    upsert into playbook_turn_stats
```

### Alert condition
Show warning when:
- `exhaustion_rate >= 0.15` (15%+ of runs hit budget) **and**
- `sample_count >= 5` (enough data)

### API endpoint

```
GET /analytics/turn-health
```

Response:
```json
[
  {
    "playbook_slug": "autopilot_full",
    "sample_count": 47,
    "p50_turns": 18,
    "p75_turns": 31,
    "p95_turns": 44,
    "exhaustion_rate": 0.34,
    "avg_max_turns": 25,
    "recommended_max": 55,
    "severity": "high"
  }
]
```

`severity`: `"high"` if exhaustion_rate >= 0.30, `"medium"` if >= 0.15, `"ok"` otherwise.

### UI surface
- **Analytics → Scorecards page**: New "Turn Budget Health" section above the grade table.
  Red/yellow badge per playbook with a tooltip: "34% of runs hit the turn limit.
  Recommended budget: 55 turns (current: 25)."
- **Canvas block editor**: If the selected playbook has `severity: high`, show an inline
  warning below the `max_turns` input: "⚠ This playbook hits its limit 34% of the time.
  Suggest: 55 turns."
- **One-click fix**: "Apply recommended budget" button sets `default_max_turns` on the workflow.

### Effort: 2 days (migration + job + API + badge UI)

---

## Feature 2: Run Similarity Search

**What**: For any failed or low-scoring run, surface the 5 most similar past successful runs.
Helps engineers see "what worked before" without digging through history manually.

**Data source**: `runs.state`, `run_traces.content`, `run_online_scores.pct`

### Requires: pgvector extension

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### New table: `run_embeddings`

```sql
CREATE TABLE run_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
    playbook_slug   TEXT NOT NULL,
    workspace_id    UUID NOT NULL,
    embedding       vector(1536) NOT NULL,   -- text-embedding-3-small
    metadata        JSONB,                   -- {trigger_type, outcome_type, grade}
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT now()
);
CREATE INDEX ON run_embeddings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ON run_embeddings (playbook_slug, workspace_id);
```

### Embedding strategy

Embed this text at run completion (in `_record_outcome()` in the executor):

```python
embed_text = f"""
playbook: {playbook_slug}
trigger: {trigger_type}
inputs: {json.dumps(truncate(trigger_payload, 500))}
outcome: {outcome_type}
summary: {state.get('_summary', '')[:800]}
"""
# Use OpenAI text-embedding-3-small (1536 dims, $0.02/1M tokens)
# Or Anthropic voyage-3 if preferred
```

Cost estimate: ~500 tokens per run × $0.02/1M = **$0.00001 per run**. Negligible.

### API endpoint

```
GET /runs/{run_id}/similar?limit=5
```

Response:
```json
[
  {
    "run_id": "abc-123",
    "playbook_slug": "autopilot_full",
    "similarity": 0.94,
    "status": "succeeded",
    "grade": "A",
    "outcome_type": "pr_opened",
    "trigger_summary": "Fix: null pointer in auth.py",
    "completed_at": "2026-06-01T14:22:00Z",
    "run_url": "/workflows/xyz/runs/abc-123"
  }
]
```

Query:
```sql
SELECT r2.id, 1 - (e2.embedding <=> e1.embedding) AS similarity, ...
FROM run_embeddings e1
JOIN run_embeddings e2 ON e2.playbook_slug = e1.playbook_slug
                       AND e2.workspace_id = e1.workspace_id
                       AND e2.run_id != e1.run_id
JOIN runs r2 ON r2.id = e2.run_id
WHERE e1.run_id = :run_id
  AND r2.status = 'succeeded'
ORDER BY similarity DESC
LIMIT 5;
```

### UI surface
- **Run detail page** (failed/low-grade runs only): Collapsible "Similar successful runs" panel
  with 5 cards showing trigger summary, grade badge, and link to that run.
- **Threshold**: Only show panel if `similarity >= 0.80` and at least 2 matches exist.

### Effort: 3 days (pgvector migration + embed worker + API + UI panel)

---

## Feature 3: Prompt Drift Detection

**What**: Track per-playbook quality score trends. If average grade drops significantly vs. the
rolling baseline without any YAML change, surface a "quality regression" alert. Catches model
update regressions before users notice.

**Data source**: `run_online_scores` (already fully populated — no new data needed)

### No new tables needed. Pure SQL aggregation.

### Detection logic (runs nightly)

```python
for slug in distinct_slugs:
    baseline_avg = avg(pct) WHERE slug = slug AND scored_at BETWEEN now()-60d AND now()-30d
    current_avg  = avg(pct) WHERE slug = slug AND scored_at > now()-7d
    baseline_n   = count WHERE same window
    current_n    = count WHERE same window

    if current_n >= 3 and baseline_n >= 5:
        drift = baseline_avg - current_avg
        if drift >= 10:  # 10 percentage-point drop
            insert/update playbook_quality_alerts
```

### New table: `playbook_quality_alerts`

```sql
CREATE TABLE playbook_quality_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    playbook_slug   TEXT NOT NULL,
    workspace_id    UUID NOT NULL,
    alert_type      TEXT NOT NULL DEFAULT 'quality_regression',
    baseline_avg    FLOAT NOT NULL,
    current_avg     FLOAT NOT NULL,
    drift_pct       FLOAT NOT NULL,          -- baseline - current (positive = decline)
    severity        TEXT NOT NULL,           -- warning / critical
    last_yaml_sha   TEXT,                    -- SHA of workflow_version at alert time
    resolved_at     TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE (playbook_slug, workspace_id, resolved_at)  -- one open alert per playbook
);
```

`severity`: `critical` if drift >= 20pp, `warning` if >= 10pp.

### API endpoint

```
GET /analytics/quality-alerts
```

Response:
```json
[
  {
    "playbook_slug": "pr_reviewer",
    "baseline_avg": 78.4,
    "current_avg": 61.2,
    "drift_pct": 17.2,
    "severity": "warning",
    "message": "Quality dropped 17pp in the last 7 days vs. 30-day baseline",
    "suggested_action": "Review recent model update notes or check prompt for stale instructions",
    "created_at": "2026-06-12T03:00:00Z"
  }
]
```

### UI surface
- **Analytics → Scorecards**: Red/amber trend arrow next to grade. Hover: "17pp quality drop
  this week vs. 30-day baseline."
- **Observability alerts feed**: Quality regression alerts appear alongside existing
  `ObservabilityAlert` items. Same `resolve` flow.
- **Slack notification** (optional): If workspace has Guard Slack configured, post to the
  same channel used for budget alerts.

### Effort: 1.5 days (table + nightly job + API + scorecard UI delta)

---

## Feature 4: Playbook Health Score (Composite)

**What**: Single 0–100 health score per playbook that combines success rate, quality, turn
efficiency, and budget safety. Replaces the need to cross-reference four separate views.

**Formula**:
```
health = (success_rate * 0.35) +
         (avg_grade_pct * 0.30) +
         (turn_efficiency * 0.20) +   # 1 - (avg_actual / max_turns), capped 0-1
         (budget_safety * 0.15)       # 1 - exhaustion_rate
× 100
```

**Data source**: `run_analytics_events`, `run_online_scores`, `playbook_turn_stats` (Feature 1)

### New table: `playbook_health_scores`

```sql
CREATE TABLE playbook_health_scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    playbook_slug   TEXT NOT NULL,
    workspace_id    UUID NOT NULL,
    score           FLOAT NOT NULL,          -- 0-100
    success_rate    FLOAT,
    avg_grade_pct   FLOAT,
    turn_efficiency FLOAT,
    budget_safety   FLOAT,
    sample_count    INTEGER,
    trend_7d        FLOAT,                   -- score delta vs. prior 7-day window
    computed_at     TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE (playbook_slug, workspace_id)
);
```

### API endpoint

```
GET /analytics/health-scores?sort=score_asc
```

Response:
```json
[
  {
    "playbook_slug": "autopilot_full",
    "score": 71.4,
    "grade": "B",
    "trend_7d": -4.2,
    "components": {
      "success_rate": 0.89,
      "avg_grade_pct": 74.1,
      "turn_efficiency": 0.61,
      "budget_safety": 0.66
    },
    "sample_count": 47
  }
]
```

### UI surface
- **Analytics → Overview**: Replace the current "Playbooks" table with a health leaderboard.
  Score column sorts by health. Color coded: green >= 75, yellow >= 50, red < 50.
- **Scorecard detail**: Show the four component bars so engineers see *what* is dragging
  the score down.

### Effort: 1.5 days (builds on Feature 1 tables + nightly job extension + UI)

---

## Feature 5: Cost Anomaly Detection

**What**: Flag individual runs that cost significantly more than the playbook's rolling average.
Catches runaway loops, prompt injection that generates massive outputs, or misconfigured tools.

**Data source**: `run_analytics_events.cost_usd` (already populated)

### No new tables. Adds a `cost_anomaly` flag to existing `RunAnalyticsEvent`.

```sql
ALTER TABLE run_analytics_events ADD COLUMN cost_z_score FLOAT;
ALTER TABLE run_analytics_events ADD COLUMN is_cost_anomaly BOOLEAN DEFAULT FALSE;
```

### Detection logic

After each run completes and `RunAnalyticsEvent` is written:
```python
recent_costs = SELECT cost_usd FROM run_analytics_events
               WHERE playbook_slug = slug AND workspace_id = ws
               AND created_at > now() - 30d
mu, sigma = mean(recent_costs), stddev(recent_costs)
z = (this_run.cost_usd - mu) / sigma if sigma > 0 else 0
is_anomaly = z >= 3.0 and len(recent_costs) >= 10
UPDATE run_analytics_events SET cost_z_score = z, is_cost_anomaly = is_anomaly WHERE id = ...
```

### API change
`GET /analytics/runs` — add `?anomalies_only=true` filter.

Dashboard `GET /dashboard` — add `cost_anomalies_today: int` to response.

### UI surface
- **Run list**: Yellow `⚠ 3.4σ` badge on anomalous runs. Click → run detail.
- **Dashboard**: "Cost anomalies today: 2" KPI card (only shown if > 0).

### Effort: 1 day (migration + inline computation hook + filter + badge)

---

## Feature 6: Auto-Fixture Suggestion (closes the eval loop)

**What**: The system already promotes low-scoring runs to `run_fixture_candidates`.
Add intelligence: rank candidates by *coverage gap* — prefer runs that test scenarios
not already covered by existing fixtures.

**Data source**: `run_fixture_candidates`, `run_embeddings` (Feature 2), eval fixture YAML files

### Logic

1. At fixture candidate insertion, embed the `anon_trigger_payload` (same embedding as Feature 2).
2. Compare against embeddings of existing fixtures for the same slug.
3. Store `novelty_score = 1 - max_cosine_similarity_to_existing_fixtures`.
4. Rank candidates by `novelty_score DESC` in the `GET /eval/candidates` response.

```sql
ALTER TABLE run_fixture_candidates ADD COLUMN novelty_score FLOAT;
ALTER TABLE run_fixture_candidates ADD COLUMN similar_fixture_id TEXT;
```

### API change
`GET /eval/candidates` — add `novelty_score` and `similar_fixture` fields. Default sort: `novelty DESC`.

### UI surface
- **Eval → Candidates table**: Add "Novelty" column. High novelty = green. Tooltip:
  "This scenario is not covered by any existing fixture — high promotion value."

### Effort: 1 day if Feature 2 (embeddings) is already built; 2 days standalone.

---

## Rollout Order

| Priority | Feature | Effort | Dependency |
|----------|---------|--------|------------|
| P0 | Feature 1: Adaptive Turn Budgets | 2d | None — pure SQL |
| P0 | Feature 3: Prompt Drift Detection | 1.5d | None — pure SQL |
| P1 | Feature 5: Cost Anomaly Detection | 1d | None |
| P1 | Feature 4: Playbook Health Score | 1.5d | Feature 1 done |
| P2 | Feature 2: Run Similarity Search | 3d | pgvector + embed budget |
| P3 | Feature 6: Auto-Fixture Suggestion | 1d | Feature 2 done |

**Total: ~10 dev-days across 3 sprints.**

---

## Shared Infrastructure

### Nightly job runner
All computation jobs attach to the existing APScheduler instance in `apps/api/app/worker.py`.
Add one `@scheduler.scheduled_job('cron', hour=3)` entry per feature.

### Alembic migrations needed
- `0010_pgvector.py` — `CREATE EXTENSION vector`
- `0011_run_embeddings.py` — new table
- `0012_turn_stats.py` — `playbook_turn_stats` table
- `0013_quality_alerts.py` — `playbook_quality_alerts` table
- `0014_health_scores.py` — `playbook_health_scores` table
- `0015_cost_anomaly_cols.py` — two columns on `run_analytics_events`
- `0016_fixture_novelty.py` — two columns on `run_fixture_candidates`

### Embedding provider
Recommend **OpenAI `text-embedding-3-small`** (1536 dims, cheapest per token).
Add `OPENAI_API_KEY` to credential vault (same pattern as GitHub token).
Alternatively: use a local `sentence-transformers` model to keep data fully on-prem.

### Guard integration
Features 1, 3, 5 surface alerts in the same Slack channel as Guard spend alerts.
Feature 4 health score feeds into Guard's "workspace health" summary (future).
