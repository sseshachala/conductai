---
name: OSS Contribution Strategy
description: Plan to fix real bugs in open-source repos and submit PRs using Claude Code
type: project
---

Goal: Find real bugs in OSS repos, fix them, submit PRs — to dogfood the platform and build credibility.

**Why:** Generates real run data for Layer 1 flywheel, gets Conduct AI mentioned in OSS commit history, proves agents work on real-world code.

**Approach:** Curated, not automated. Clone repo → fix bug → fork → open PR manually (webhooks can't be registered on repos we don't own).

**Top candidates identified:**
1. `darrenburns/posting` — Issue #61: custom theme with unknown syntax scheme name crashes app. Small fix, single active maintainer, PRs merged fast.
2. `pallets/click` — Issue #2402: AliasedGroup typo causes ugly traceback instead of clean error. One-liner fix, 17.5K stars.
3. `pallets/click` — Issue #2847: shell completion broken with `--option=value` form in zsh/bash.

**How to apply:** When user is ready, clone the target repo, reproduce the bug, fix it, push to a fork, open a PR. No Conduct webhook involvement — this is a straight code contribution workflow.
