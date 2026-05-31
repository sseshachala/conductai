---
name: Workspace Management
description: Set up, configure, and audit the Rundock workspace
---

Manage the Rundock workspace: initial setup, configuration updates, and health checks.

## Setup (new or existing workspace)

**Read before asking.** Before asking the user anything:
- Read `CLAUDE.md` if it exists
- Run `ls` on the workspace root and key directories
- Check `.claude/settings.json` for tool permissions, hooks, and MCP servers
- Check `.claude/skills/` and `.claude/agents/` for existing capabilities
- Summarise what you found. Propose a plan based on what already exists.

Only ask about things the files don't answer:
- Who will use it (just the user, or a team)?
- Any tools or integrations not already visible in the config?

### Create or update CLAUDE.md

Write a `CLAUDE.md` at the workspace root with:
- Clear heading with the workspace name
- What the workspace is for
- Key rules and conventions
- File structure and naming patterns
- Tool or integration notes

Keep it concise. CLAUDE.md should be a quick reference, not a manual.

### Set up folder structure

Suggest the best-fit structure based on the workspace purpose:

**PARA** (personal productivity, knowledge management):
- `0 Inbox/`, `1 Projects/`, `2 Areas/`, `3 Resources/`, `4 Archive/`

**Functional** (business or team workspaces):
- Organised by domain: `Clients/`, `Operations/`, `Finance/`, `Marketing/`, etc.

**Minimal** (lightweight, low-maintenance):
- `Inbox/`, `Working/`, `Reference/`

Let the user choose or adapt. Don't impose a structure they won't maintain.

## Audit (workspace health check)

Run this when the user asks "how's my workspace?" or "review my setup."

### Check workspace fundamentals
- [ ] CLAUDE.md exists and is current (not stale or generic)
- [ ] Folder structure matches the workspace's actual use
- [ ] `.claude/agents/` exists with at least one agent
- [ ] `.claude/settings.json` has appropriate permissions

### Check skill completeness

For every skill file in `.claude/skills/`:

1. **Frontmatter fields.** Each skill file must have a YAML frontmatter block with `name` and `description` fields. Flag any skill missing either field.
2. **Body content.** The content after the frontmatter closing `---` must be non-empty. Flag skills that are stubs (frontmatter only, no instructions).

How to check:
- Read each `SKILL.md` file in `.claude/skills/*/`
- Parse the YAML frontmatter between the opening and closing `---`
- Verify `name:` is present and non-empty
- Verify `description:` is present and non-empty
- Verify there is meaningful content after the closing `---` (not just whitespace)

Example finding: "Your 'meeting-prep' skill is missing a description. Want me to add one based on the file contents?"
Example finding: "The 'data-export' skill is a stub with no instructions. Want me to flesh it out based on its name and description?"

### Check path consistency

Verify that references between agents and skills resolve to real files.

1. **Skill slug references in agents.** For each agent file in `.claude/agents/`, scan the body text for skill slugs (the folder names in `.claude/skills/`). If an agent references a slug that doesn't exist as a skill directory, flag it as a broken reference.
2. **Agent reportsTo references.** If an agent's frontmatter contains a `reportsTo` field, verify the referenced agent ID matches an actual agent file. Flag broken `reportsTo` chains.
3. **Skill file paths.** For each skill, verify the skill directory contains the expected `SKILL.md` file. Flag directories that exist but are missing their definition file.

How to check:
- List all directories in `.claude/skills/` to build a skill slug inventory
- List all files in `.claude/agents/` to build an agent ID inventory
- For each agent file, read its body and check for skill slug mentions using word-boundary matching
- For each agent's `reportsTo` value, check it appears in the agent inventory
- For each skill directory, check `SKILL.md` exists

Example finding: "Your agent 'penny' references a skill slug 'content-review', but there's no `.claude/skills/content-review/` directory. Was this renamed or deleted?"
Example finding: "Agent 'dev' has `reportsTo: ops-lead`, but there's no agent with that ID. Want me to update it?"

### Check team coverage
- [ ] Every skill in `.claude/skills/` is assigned to at least one agent
- [ ] No orphan skills (skill exists but no agent references it)
- [ ] No phantom references (agent references a skill slug that doesn't exist)
- [ ] Skill assignment doesn't overlap (each skill owned by exactly one agent)

### Check overall health
- [ ] Exactly one orchestrator agent
- [ ] Orchestrator delegates Rundock operations to Doc
- [ ] All specialists have routing boundaries
- [ ] No raw/unupgraded agents in Available

### Report

Present findings conversationally. Don't dump a raw checklist. For each finding:
1. State what's wrong in plain language
2. Explain why it matters (briefly)
3. Offer to fix it

Group by severity, but keep the tone helpful, not clinical:
- **Issues (must fix):** Broken references, missing agents, structural problems
- **Warnings (should fix):** Stale CLAUDE.md, unassigned skills, stub skills, thin coverage
- **Good:** What's working well

Example tone: "I found 3 things worth fixing and 2 that could be better. The good news: your core setup is solid. Here's what I'd tidy up..."

Offer to fix each issue. For agent or skill changes, use the appropriate Rundock markers.
