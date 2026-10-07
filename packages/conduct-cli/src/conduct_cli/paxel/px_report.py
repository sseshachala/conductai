"""paxel report: split out of the original single-file paxel.py."""

import json
import os

from px_base import OUT_DIR
from px_scoring import _d10


def bar(n, mx, width=28):
    if mx <= 0:
        return ""
    return "█" * max(1, round(n / mx * width)) if n else ""


def write_report(s):
    L = []
    A = L.append
    c = s["corpus"]; v = s["volume"]; t = s["tools"]; vel = s["velocity"]
    b = s["behavior"]; r = s["rhythm"]; st = s["stack"]; au = s["autonomy"]
    A("# Local Paxel — Builder Stats Report\n")
    A(f"_Scope: {s['scope']}. Generated entirely on-device — nothing uploaded._\n")
    A("## Corpus")
    if c.get("sources"):
        A("- Sources: " + ", ".join(
            f"**{name}** ({d['files']} files, {d['sessions']} sessions, {d['prompts']:,} prompts)"
            for name, d in c["sources"].items()))
    A(f"- Transcripts parsed: **{c['files_parsed']}** ({c['lines_total']:,} events, "
      f"{c['lines_unparseable']} unparseable)")
    A(f"- Date range: **{_d10(c['date_range'][0])} → {_d10(c['date_range'][1])}** "
      f"({c['span_days']} days span, **{c['active_days']} active days**)")
    A(f"- Timezone: {c['timezone']}\n")
    A("## Volume")
    A(f"- Sessions: **{v['total_sessions']}**")
    A(f"- Genuine prompts (human-typed): **{v['total_prompts']:,}**  "
      f"(+{v['command_invocations']} slash-command invocations)")
    A(f"- Avg prompt length: **{v['avg_prompt_length_chars']:.0f} chars** "
      f"(median {v['median_prompt_length_chars']:.0f})")
    A(f"- Assistant turns: {v['assistant_turns']:,} · tool calls: **{v['tool_calls_total']:,}** "
      f"· thinking blocks: {v['thinking_blocks']:,}\n")
    A("## Tools")
    A(f"- Tool diversity: **{t['tool_diversity']} distinct tools** "
      f"(normalized entropy {t['tool_entropy_normalized']})")
    A(f"- MCP share: **{t['mcp_share']*100:.0f}%** ({t['mcp_calls']:,} MCP / {t['native_calls']:,} native)")
    A("- Top tools:")
    mx = t["top_tools"][0][1] if t["top_tools"] else 1
    for name, cnt in t["top_tools"]:
        A(f"  - `{name}` · {cnt:,} {bar(cnt, mx)}")
    A(f"- Category mix: {t['category_breakdown']}\n")
    A("## Code velocity")
    A(f"- **Git churn (gold standard): {vel['git_churn_total']:,} lines** "
      f"(+{vel['git_insertions']:,} / -{vel['git_deletions']:,}) across {vel['git_commits_real']:,} commits "
      f"in {vel['git_repos_with_commits']}/{vel['git_repos_seen']} repos on disk")
    A(f"  - **{vel['git_velocity_lines_per_hour']:.0f} lines/hour** over {vel['active_hours']:,} active hours")
    if vel.get("git_per_repo"):
        A("  - By repo: " + ", ".join(f"{n} ({i+d:,})" for n, i, d, _c in vel["git_per_repo"][:6]))
    _gtot, _ttot = vel['git_churn_total'], max(vel['tool_churn_edit_write'], 1)
    _missing = vel['git_repos_seen'] - vel['git_repos_with_commits']
    if _missing > 0:
        _cov = (f" — note this is **partial**: only {vel['git_repos_with_commits']} of "
                f"{vel['git_repos_seen']} repos were counted (the rest are missing from disk, have no "
                f"commits under your git email, or were too large to scan in time). "
                f"The Execution score nudges its throughput term up modestly (≤1.4×) to avoid "
                f"penalizing you for repos paxel couldn't read")
    else:
        _cov = ""
    A(f"- Tool-only churn (Edit/Write — what most profilers see): {vel['tool_churn_edit_write']:,} lines. "
      f"Git/tool ratio: **{_gtot/_ttot:.1f}×**{_cov}")
    A(f"- Shell-authored work the Edit/Write path misses entirely: {vel['shell_write_calls']:,} file-writing Bash "
      f"calls, ~{vel['shell_authored_lines_est']:,} lines of heredoc/redirect content\n")
    A("## Behavior")
    A(f"- Planning ratio (explore : doing): **{b['planning_ratio_explore_to_doing']}** "
      f"(explore {b['explore_actions']:,} vs doing {b['produce_actions']+b['execute_actions']+b['delegate_actions']:,})")
    A(f"- Avg session: **{b['avg_session_minutes']:.0f} min** (median {b['median_session_minutes']:.0f})")
    A(f"- Errors: **{b['tool_errors']:,} tool errors** ({b['error_rate_per_100_tools']} per 100 tool calls); "
      f"{b['recovered_errors']:,} recovered ({b['error_recovery_ratio']*100:.0f}%); {b['api_errors_retries']} API retries")
    A(f"- Iteration depth (edits/file before commit): mean **{b['iteration_depth_mean']:.1f}**, "
      f"median {b['iteration_depth_median']:.0f}, p90 {b['iteration_depth_p90']}, "
      f"**max {b['iteration_depth_max']}** — {b['files_hammered_over_15x']} files hammered >15× in one session")
    A(f"- Actions per prompt: **{b['actions_per_prompt']:.1f}** · "
      f"questions asked: {b['questions_asked']} · background: {b['background_tasks']} · scheduled: {b['scheduled_actions']}\n")
    A("## Rhythm")
    A(f"- Peak hours (local): **{', '.join(f'{h:02d}:00' for h in r['peak_hours_local'])}**")
    A(f"- Preferred days: **{', '.join(r['preferred_days'])}**")
    A("- Hours:")
    hh = r["hour_histogram_local"]; hmx = max(hh.values()) if hh else 1
    for h in range(24):
        n = hh.get(str(h), 0)
        A(f"  - {h:02d} {bar(n, hmx, 24)} {n}")
    A("- Days:")
    wd = r["weekday_histogram"]; wmx = max(wd.values()) if wd else 1
    for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
        n = wd.get(d, 0)
        A(f"  - {d} {bar(n, wmx, 24)} {n}")
    A("")
    A("## Stack")
    A(f"- Models: {', '.join(f'{m} ({n})' for m, n in st['models'][:6])}")
    A(f"- Top skills: {', '.join(f'{k} ({n})' for k, n in st['top_skills'][:10]) or '—'}")
    A(f"- Subagent types: {', '.join(f'{k} ({n})' for k, n in st['subagent_types']) or '—'}")
    A("- Top projects (events, sessions):")
    for name, cnt, sess in st["top_projects"]:
        A(f"  - {name} · {cnt:,} events · {sess} sessions")
    A("")
    A("## Autonomy")
    A(f"- **Autonomy score: {au['autonomy_score_0_100']}/100**")
    A(f"- Components: {au['components']}")
    with open(os.path.join(OUT_DIR, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def write_narrative_input(s, opening_prompts, longest_prompts):
    L = []
    A = L.append
    A("# Narrative input (LOCAL ONLY — for the archetype/traits pass)\n")
    A("Full metrics:\n```json")
    A(json.dumps(s, indent=2, default=str))
    A("```\n")
    A("## Opening prompts (first human message per session — characteristic asks)\n")
    op = [p for p in opening_prompts if p[0] is not None]
    op.sort(key=lambda x: x[0])
    # spread a sample across the timeline
    sample = op[:: max(1, len(op) // 60)] if op else []
    for dt, proj, text in sample[:60]:
        A(f"- [{dt.date()} · {proj}] {text.replace(chr(10), ' ')[:280]}")
    A("\n## Longest prompts (most detailed specs)\n")
    longest_prompts.sort(key=lambda x: -x[0])
    for ln, proj, text in longest_prompts[:20]:
        A(f"- [{ln} chars · {proj}] {text.replace(chr(10), ' ')[:280]}")
    with open(os.path.join(OUT_DIR, "narrative_input.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


# ---------------------------------------------------------------------------
# User-facing profile: a transparent rubric turns the measured metrics into an
# archetype + 0-10 scores (no LLM needed), then we emit a branded, shareable
# profile.html. The COUNTS are measured; the scores/archetype are a rubric and
# the report says so. narrative_input.md is still written for optional LLM polish.
#
# The three score axes are NOT an arbitrary rubric — each one is grounded in
# Garry Tan's open-source gstack (github.com/garrytan/gstack), the same
# Garry-Tan-world framework YC's Paxel comes out of. gstack frames building as a
# sprint — Think → Plan → Build → Review → Test → Ship → Reflect — on top of
# three ethos pillars: "Boil the Lake" (completeness is cheap, do the complete
# thing), "Search Before Building" (know what exists first), and "User
# Sovereignty" (AI recommends, the human decides — and per Anthropic's own
# research, experts interrupt MORE, not less). Each axis below maps a slice of
# that framework onto the metrics paxel can honestly measure from transcripts.
#
# The rubric was then AUDITED by running the real installed gstack skills
# (/plan-eng-review, /plan-ceo-review, /review) via independent subagents. That
# audit drove the current design: each metric is owned by EXACTLY ONE axis (so no
# two axes silently move together), and a 5th "Product Instinct" axis was CUT — the
# audit showed it was mostly skill-detection plus terms recycled from other axes, i.e.
# it didn't honestly measure product judgment. Coding transcripts don't reveal that, so
# we don't fake it. A later validity pass then DEMOTED a 4th axis, Steering, from a
# scored 0–10 to a described reading (see steering_reading): hands-on cadence is real
# but has no good/bad end, and grading it `(15 - actions_per_prompt)` ran backwards
# (a more autonomous engineer scored lower). So: 3 graded axes + 1 described.
# ---------------------------------------------------------------------------
REPO_URL = "https://github.com/Photobombastic/paxel-local"

# Plain-language explanation shown under each score bar — what the axis measures, in
# human terms, no jargon. (The gstack grounding lives in the disclaimer + README, not here.)
SCORE_NOTES = {
    "Execution": "How much you ship, and how fast — your committed-code rate, how much of what "
                 "you generate actually lands in git, and how hard you delegate to agents.",
    "Planning": "How much you think before you build — exploring before writing, reasoning "
                "depth, and laying out a plan first. (Prompt length was dropped — terse expert "
                "prompts shouldn't score below verbose ones.)",
    "Engineering": "How clean your work is — getting files right early, not re-editing the same "
                   "one over and over, low error rate, and checking your work.",
}

# One-line versions of the axis notes for the shareable poster image — the full SCORE_NOTES
# don't fit on a single line under a bar on the card.
SCORE_NOTES_SHORT = {
    "Execution": "Shipped output, at AI leverage",
    "Planning": "Think before you build",
    "Engineering": "Craft, with little rework",
}
