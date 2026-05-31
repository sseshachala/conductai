---
name: Skill Management
description: Create, edit, delete, and audit skills
---

Manage skills in `.claude/skills/`. This skill covers the full lifecycle.

## Important: file access

Claude Code blocks Write and Edit tools for files inside `.claude/`. Do NOT use Write, Edit, or Bash to create, modify, or delete skill files. Instead, use RUNDOCK markers. The Rundock client detects these markers in your response and saves the files through the server.

## Create a skill

### 1. Understand the skill

Ask the user:
- What should this skill do? (purpose, when it triggers)
- Which agent should own it? (check `.claude/agents/` for the current team)

If the user already provided enough detail, skip straight to drafting.

### 2. Draft the skill

A good skill file has:
- **Clear trigger:** When should the agent use this skill? Be specific about the user request or situation.
- **Step-by-step instructions:** Numbered steps, not prose paragraphs. Each step should be a concrete action.
- **File references:** Specific paths the skill reads from or writes to. Run `ls` if unsure what exists.
- **Output format:** What the result should look like (structure, length, tone).
- **Boundaries:** What the skill does NOT cover. Which other skill or agent handles adjacent requests.

**Naming:** Slugs are lowercase with hyphens: `meeting-prep`, `weekly-digest`, `code-review`.

### 3. Save the skill

Output the complete skill file wrapped in the marker:

<!-- RUNDOCK:SAVE_SKILL name={slug} -->
```
---
name: {Human Readable Name}
description: {What this skill does}
---

{Skill instructions}
```
<!-- /RUNDOCK:SAVE_SKILL -->

The skill will be saved to `.claude/skills/{slug}/SKILL.md`. The skills panel updates automatically.

### 4. Assign to an agent

After creating the skill, update the owning agent's instructions to reference the skill slug. This is how Rundock connects skills to agents in the UI.

Tell the user: "To connect this skill to [agent name], I need to update their instructions to reference `{slug}`. Want me to do that?"

If yes, read the agent file from `.claude/agents/{agent-slug}.md`, add the skill reference to the appropriate section, and output the updated agent file using:

<!-- RUNDOCK:SAVE_AGENT name={agent-slug} -->
```
{updated agent file}
```
<!-- /RUNDOCK:SAVE_AGENT -->

**Rule:** Each skill should be assigned to exactly one agent. If two agents could own it, pick the one whose core purpose aligns best.

## Edit a skill

1. Read the current skill file from `.claude/skills/{slug}/SKILL.md`
2. Make the requested changes
3. Output the complete updated file using the SAVE_SKILL marker
4. Confirm what changed

## Delete a skill

Output the delete marker:

<!-- RUNDOCK:DELETE_SKILL name={slug} -->

Confirm: "Skill `{slug}` has been removed."

If any agents referenced this skill, suggest updating their instructions to remove the reference.

## Audit skills

Review all skills for quality and consistency.

### Per-skill checks
- [ ] Has a clear, specific purpose (not a vague description)
- [ ] Instructions are step-by-step, not a wall of prose
- [ ] File paths reference real workspace locations (verify with `ls`)
- [ ] Output format is defined
- [ ] Boundaries are defined (what it doesn't cover)
- [ ] Slug matches naming convention (lowercase, hyphens, no spaces)
- [ ] No em dashes or en dashes
- [ ] UK spelling throughout
- [ ] Assigned to exactly one agent (agent instructions reference the slug)

### Cross-skill checks
- [ ] No overlapping responsibilities between skills
- [ ] No orphan skills (exists but no agent references it)
- [ ] No phantom references (agent references a slug that doesn't exist)
- [ ] Skills grouped logically by agent domain

### Report and fix

Present findings as **Issues** (must fix), **Warnings** (should fix), **Good** (working well).

Offer to fix each issue. Output corrected skill files using the SAVE_SKILL marker, one at a time. For assignment issues, also update the relevant agent file using the SAVE_AGENT marker.

## Quality checklist (for all operations)

Before outputting any SAVE_SKILL marker, verify:
- [ ] Skill has a clear, specific purpose
- [ ] Instructions are step-by-step
- [ ] File paths reference real workspace locations
- [ ] Slug matches naming convention
- [ ] No em dashes or en dashes
- [ ] UK spelling throughout
- [ ] Frontmatter includes name and description
