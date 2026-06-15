# AI Governance Playbooks

Governance embedded in the workflow, not added afterward. The 4 playbooks map to the full AI governance lifecycle — from before you deploy a tool, while teams use it, and when things break.

---

## The Lifecycle

```
BEFORE YOU DEPLOY
└── AI Risk Assessment (manual, one-time per tool)

WHILE TEAMS USE IT  
├── AI Output Auditor (weekly)
└── Drift Detector (daily, silent on healthy days)

WHEN THINGS BREAK
└── Incident Drill (quarterly)
```

---

## 1. AI Risk Assessment

**When:** Before rolling out any AI tool to a team  
**Trigger:** Manual  
**Cadence:** One-time per tool

**What it does:**  
7-step pre-deploy checklist that surfaces risks, sets data boundaries, defines human controls, and builds a one-page incident response plan. Think of it as your security + ops sign-off for new AI tooling.

| Step | What you get |
|---|---|
| 1. Threat model | Identify data exposure, hallucination, and misuse risks |
| 2. Data boundaries | Define what data the tool can see / can't touch |
| 3. Human controls | Who reviews outputs? Who can override? How? |
| 4. Fallback plan | What happens if the tool fails or misbehaves? |
| 5. Budget baseline | Expected monthly spend + warning thresholds |
| 6. Incident triggers | What counts as a problem? (accuracy drop, breach, cost spike) |
| 7. Response runbook | Who to notify, what to do, rollback steps |

**Output:**  
- Full assessment report sent to Slack
- GitHub tracking issue with action items and sign-off requirements

---

## 2. AI Output Auditor

**When:** Weekly, once the tool is deployed  
**Trigger:** Scheduled webhook  
**Cadence:** Weekly

**What it does:**  
Samples AI output patterns, scores quality and bias signals (0-100), detects over-reliance, and posts a governance scorecard. Runs silently in the background — you only see it weekly.

| Signal | What it measures |
|---|---|
| Quality score | Accuracy, completeness, hallucination rate |
| Bias score | Output fairness across user types, edge cases |
| Over-reliance | How many decisions rely on tool output vs human review |
| Degradation | Quality trending down? Flag it |

**Output:**  
Weekly scorecard to Slack with **GO** / **WATCH** / **ACT** signal:
- **GO** — All signals green, no action needed
- **WATCH** — One signal yellow; monitor next week
- **ACT** — One or more signals red; review outputs, retrain, or restrict access

---

## 3. Drift Detector

**When:** Daily  
**Trigger:** Scheduled webhook  
**Cadence:** Daily (silent on healthy days)

**What it does:**  
Monitors usage patterns against baseline. Catches policy violation spikes, budget anomalies, shadow usage, and quality drops. Only alerts when drift threshold is breached — keeps noise low.

| Drift type | What triggers an alert |
|---|---|
| Policy violations | Sudden spike in blocked calls or warnings |
| Budget anomalies | Usage 20%+ above baseline for the day |
| Shadow usage | Tool calls from unauthorized users or teams |
| Quality drops | Output quality score drops 15+ points in 24h |

**Output:**  
Slack alert only when drift threshold is breached. Alert includes:
- What drifted (policy? spend? quality?)
- By how much
- Recommended action (investigate, roll back, restrict)

---

## 4. Incident Drill

**When:** Quarterly  
**Trigger:** Manual  
**Cadence:** Quarterly

**What it does:**  
Simulates a realistic AI incident scenario. Scores your response plan, identifies gaps, and grades readiness. Runs a controlled "what if?" to catch blind spots before they happen in production.

| Scenario type | Example |
|---|---|
| Data leak | An AI tool accidentally outputs PII in a team chat |
| Hallucination in prod | Tool generates incorrect info that customer sees |
| Budget breach | Usage spikes 10x in one day; costs hit hard cap |
| Unauthorized usage | Someone uses the tool outside their approved scope |
| Model behaviour change | Claude API behavior changes mid-month; tool output degrades |

**Output:**  
- Readiness score (0-100)
- Letter grade (A-F)
- Gap analysis: what part of your incident plan failed?
- Slack summary with action items to close gaps

---

## Running the Full Lifecycle

### Setup (one-time)

1. **Install all 4 playbooks** from the Governance category in the Conduct marketplace
2. Run **AI Risk Assessment** before first deployment — this generates the incident response plan the Drill will test

### Ongoing operations

3. **Configure Output Auditor** with a weekly webhook
   - Set webhook trigger to run every Monday at 8am (or your preferred day)
   - Configure in ConductGuard dashboard: Integrations → Webhooks → Add
4. **Configure Drift Detector** with a daily webhook
   - Set webhook trigger to run daily at midnight UTC
   - Configure baseline thresholds (e.g., "alert if 20% spend increase")
5. **Run Incident Drill quarterly**
   - Pick a scenario (data leak, hallucination, budget, etc.)
   - Score readiness
   - Close gaps identified
   - Re-run next quarter to verify improvements

---

## Why This Order Matters

**AI Risk Assessment first.** You can't audit what you haven't defined. The assessment creates the baseline — what's "normal" spend, what data should flow, what quality looks like. Output Auditor and Drift Detector measure against this baseline.

**Output Auditor + Drift Detector together.** Auditor catches slow degradation (quality dropping 1% per week). Drift Detector catches spikes (budget 10x overnight). Both weekly/daily; both post to Slack. One catches gradual rot, one catches black swans.

**Incident Drill last.** By the time you run the Drill, you have 3 months of baseline data + weekly audits + daily drift alerts. The Drill tests if your team *actually knows what to do* when one of those alerts fires. Readiness score tells you if you're ready for production.

---

## Integration Examples

### Slack integration

```
Weekly Output Auditor report:
📊 AI Output Governance — Week of June 14
├── Quality: 92 (GO)
├── Bias: 78 (WATCH — check edge cases)
├── Over-reliance: 65 (GO)
└── Action: Review 3 low-quality outputs from Tuesday

Daily Drift Detector alert (only if threshold breached):
🚨 Drift Alert
├── Policy violations: 5 blocks/day → 12/day (spike!)
├── Recommended: Review recent changes to tool config
└── Timeline: Incident Drill readiness check started
```

### GitHub integration

```
Issue: AI Risk Assessment — Claude Code Deploy
├── Pre-deploy checklist: 7/7 steps complete
├── Incident response plan: Attached as RUNBOOK.md
├── Approvals: @sec-lead, @ops-lead
├── Status: Ready for deploy (action items tracked below)
```

### Webhook trigger (cron)

ConductGuard playbooks integrate with standard cron schedulers or GitHub Actions. Example with `cron-job.org`:

```
Weekly (Monday 8am UTC):
POST https://api.conductguard.io/v1/playbooks/output-auditor/run?token=...

Daily (midnight UTC):
POST https://api.conductguard.io/v1/playbooks/drift-detector/run?token=...

Quarterly (manual or calendar-based):
POST https://api.conductguard.io/v1/playbooks/incident-drill/run?token=...&scenario=data_leak
```

---

## Related Docs

- [ConductGuard Overview](overview.md) — High-level architecture and concepts
- [Spend Controls](spend_controls.md) — Budget configuration, hard caps, per-developer limits
- [Roles & Permissions](roles_permissions.md) — Who can configure playbooks, run drills, approve exceptions
- [Developer Setup](developer_setup.md) — How developers receive and run under governance policies
- [Team Onboarding](team_onboarding.md) — Onboarding a new team into ConductGuard

