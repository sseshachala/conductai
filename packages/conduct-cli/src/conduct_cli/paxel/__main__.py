#!/usr/bin/env python3
"""
paxel-local: a fully-local recreation of YC's Paxel builder-profile tool.

Paxel reads your AI coding-agent session transcripts and emits a "how you build
with AI" profile. The catch: it ships transcript-derived content to YC's LLM
proxy and uploads narratives + metadata to YC (readable by any YC employee,
retained indefinitely). This recreation does the same analysis with ZERO data
leaving your machine:

  - This script computes the metrics Paxel reports, deterministically, from
    ~/.claude/projects/**/*.jsonl  (Claude Code transcripts).
  - The qualitative half (Builder Archetype, Autonomy, standout traits) is written
    by YOUR OWN Claude/GPT session, reading narrative_input.md locally — i.e. the
    local stand-in for the LLM Paxel would otherwise send your data to.

Usage:
    python3 paxel/              # reads ~/.claude/projects, writes outputs next to paxel/

No dependencies beyond the Python 3 standard library. No NETWORK calls anywhere.
For accurate "gold-standard" churn it shells out to the local `git` CLI to read
`git log --numstat` on repos found in your transcripts — this captures every
committed change however it was made (Edit, Bash heredoc, sed, vim...), not just
the Edit/Write tool path. That git read is 100% on-device; nothing is uploaded.

Outputs (in the directory containing paxel/):
  - stats.json          machine-readable metrics
  - report.md           deterministic stats report (human-readable)
  - narrative_input.md  curated, LOCAL-ONLY excerpts for the narrative pass
                        (may contain names/PII from your prompts — keep local)

Sources: Claude Code, Codex CLI, Gemini CLI, Pi, opencode, and Cursor (auto-detected).
Restrict with args, e.g. `python3 paxel/ claude` for Claude-only; no args = all
detected. One-shot; just re-run to rebuild as sessions accumulate.
"""

import contextlib
import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime

from px_base import ALL_SOURCES, ASK_TOOLS, OUT_DIR, SCHEDULE_TOOLS, _FILLER, _POLITE_RE, _RAGE_RE, _crashout_score, _cryptic_score, _open_in_browser, _safe_quote, bash_runs_tests, bash_writes_file, classify_tool, git_churn, line_count, parse_ts, pctile, strip_injections
from px_cursor import _cursor_dedup
from px_html import write_profile_html
from px_report import REPO_URL, write_narrative_input, write_report
from px_scoring import compute_scores, pick_archetype
from px_sources import discover_sources, iter_events


def main():
    # Sources to analyze: pass names as args (e.g. `python3 paxel/ claude`) to
    # restrict; default is every detected source. ("claude" keeps it to your own
    # Claude Code work; omit args to fold in Codex + Gemini too.)
    selected = [a.lower() for a in sys.argv[1:] if not a.startswith("-")] or list(ALL_SOURCES)
    unknown = [s for s in selected if s not in ALL_SOURCES]
    if unknown:
        print(f"  warning: unknown source(s) {unknown} ignored; valid: {', '.join(ALL_SOURCES)}")
    sources = discover_sources(selected)
    by_src = Counter(s for s, _, _ in sources)
    print(f"Found {len(sources)} transcript files across "
          f"{', '.join(f'{k}:{v}' for k, v in by_src.items()) or 'no sources'}")
    sources, cursor_twins = _cursor_dedup(sources)
    if not sources:
        print("\n  No transcripts found in ~/.claude/projects, ~/.codex/sessions, "
              "~/.gemini/tmp, ~/.pi/agent/sessions, ~/.local/share/opencode/storage, "
              "or ~/.cursor/projects.")
        print("  Nothing to analyze — run this where you've actually used a coding agent.")
        return

    # ---- accumulators --------------------------------------------------------
    files_parsed = 0
    lines_total = 0
    lines_bad = 0

    session_ts = defaultdict(list)   # sessionId -> [epoch seconds]
    session_files = defaultdict(set)
    GAP_CAP_S = 600                   # cap idle gaps at 10 min when summing active time

    prompts_count = 0
    polite_prompts = 0         # prompts that say please / thanks / etc.
    prompt_lengths = []        # chars of genuine typed prompts
    # "In your own words" cards — pulled VERBATIM from real prompts (local page only,
    # never the shared image). go-to phrase / most cryptic / biggest crash-out.
    phrase_counts = Counter()      # normalized short prompt -> times seen
    phrase_repr = {}               # normalized -> first original spelling
    phrase_sess = defaultdict(set) # normalized -> session ids it appeared in
    cryptic_cands = []             # [(score, verbatim text)] — ranked at the end
    crashout_cands = []            # [(score, verbatim text)]
    command_invocations = 0

    assistant_turns = 0
    text_blocks = 0
    thinking_blocks = 0
    thinking_chars = 0
    tool_use_total = 0
    tool_counter = Counter()
    cat_counter = Counter()    # explore/produce/execute/delegate/ask/other
    mcp_calls = 0
    native_calls = 0

    model_counter = Counter()
    skill_counter = Counter()
    subagent_counter = Counter()
    project_activity = Counter()   # cwd -> events
    project_sessions = defaultdict(set)

    lines_added = 0
    lines_removed = 0
    edits_per_file_events = []      # iteration depth samples (edits to a file before commit)
    git_commits = 0
    background_tasks = 0
    scheduled_actions = 0
    questions_asked = 0

    tool_errors = 0
    api_errors = 0
    recovered_errors = 0

    bash_write_calls = 0       # Bash calls that write/modify a file
    bash_authored_lines = 0    # newlines inside those commands (shell-authored content estimate)
    shell_test_runs = 0        # Bash calls that run a test suite (pytest/go test/npm test/…) — CLI TDD

    hour_hist = Counter()          # local hour 0-23
    weekday_hist = Counter()       # 0=Mon..6=Sun
    date_set = set()
    all_min_dt = None
    all_max_dt = None

    # narrative samples
    opening_prompts = []           # (dt, project, text) first genuine prompt per session
    longest_prompts = []           # kept small via periodic trim

    seen_session_open = set()
    source_files = Counter()             # source -> files
    source_sessions = defaultdict(set)   # source -> sessionIds
    source_prompts = Counter()           # source -> genuine prompts

    for cur_src, fp, fmt in sources:
        files_parsed += 1
        source_files[cur_src] += 1
        if files_parsed % 300 == 0:
            print(f"  ...{files_parsed}/{len(sources)}")
        # per-session, per-file ordered state for error-recovery + iteration depth
        pending_error = defaultdict(bool)        # sessionId -> unrecovered error flag
        file_edit_run = defaultdict(lambda: defaultdict(int))  # session -> file -> edits since commit

        # iter_events() yields Claude-shaped event dicts for every source format,
        # so the per-event logic below is identical across all supported sources.
        with contextlib.nullcontext(
                iter_events(fp, fmt, cursor_twins=cursor_twins)) as _evs:
            for ev in _evs:
                if ev.get("__bad__"):
                    lines_bad += 1
                    continue
                lines_total += 1

                etype = ev.get("type")
                sid = ev.get("sessionId")
                cwd = ev.get("cwd")
                dt = parse_ts(ev.get("timestamp"))

                if dt is not None:
                    if all_min_dt is None or dt < all_min_dt:
                        all_min_dt = dt
                    if all_max_dt is None or dt > all_max_dt:
                        all_max_dt = dt
                    hour_hist[dt.hour] += 1
                    weekday_hist[dt.weekday()] += 1
                    date_set.add(dt.date().isoformat())
                    if sid:
                        session_ts[sid].append(dt.timestamp())
                if sid:
                    session_files[sid].add(fp)
                    source_sessions[cur_src].add(sid)
                if cwd:
                    project_activity[cwd] += 1
                    if sid:
                        project_sessions[cwd].add(sid)

                msg = ev.get("message") if isinstance(ev.get("message"), dict) else None

                # ---- API error / retry events (system + assistant) ----------
                if ev.get("isApiErrorMessage") or ev.get("apiErrorStatus"):
                    api_errors += 1
                if etype == "system" and ev.get("retryAttempt"):
                    api_errors += 1

                # ---- genuine user prompts -----------------------------------
                if etype == "user" and msg is not None:
                    if (ev.get("isMeta") or ev.get("isCompactSummary")
                            or ev.get("isVisibleInTranscriptOnly") or ev.get("isSidechain")):
                        pass  # injected / non-human / subagent-dispatch instruction
                    else:
                        content = msg.get("content")
                        text = None
                        if isinstance(content, str):
                            text = content
                        elif isinstance(content, list):
                            parts = [b.get("text", "") for b in content
                                     if isinstance(b, dict) and b.get("type") == "text"]
                            if parts:
                                text = "\n".join(parts)
                        if text is not None:
                            is_command = ("<command-name>" in text or
                                          text.lstrip().startswith("<local-command"))
                            cleaned = strip_injections(text)
                            if is_command and not cleaned:
                                command_invocations += 1
                            elif cleaned:
                                prompts_count += 1
                                source_prompts[cur_src] += 1
                                prompt_lengths.append(len(cleaned))
                                if _POLITE_RE.search(cleaned):
                                    polite_prompts += 1
                                # collect verbatim-quote candidates (short prompts only, and
                                # only if safe to surface — no secrets / no harness markers)
                                _wc = len(cleaned.split())
                                if _safe_quote(cleaned) and 1 <= _wc <= 6:
                                    _norm = re.sub(r"\s+", " ", cleaned.strip().lower()).strip("?.!,. ")
                                    if len(_norm) >= 2:
                                        phrase_counts[_norm] += 1
                                        phrase_repr.setdefault(_norm, cleaned.strip())
                                        phrase_sess[_norm].add(sid)
                                if _safe_quote(cleaned):
                                    if 3 <= _wc <= 14:
                                        _words = re.findall(r"[a-z']+", cleaned.lower())
                                        if _words and not all(w in _FILLER for w in _words):
                                            _csc = _cryptic_score(cleaned)
                                            if _csc >= 1.8:
                                                cryptic_cands.append((round(_csc, 2), cleaned.strip()))
                                    if sum(c.isalpha() for c in cleaned) >= 6 and _wc <= 16:
                                        _bangs = cleaned.count("!") + cleaned.count("?")
                                        # gate: must read NEGATIVE (frustration word or !!-level
                                        # punctuation) — caps alone is excitement, not a crash-out
                                        if _RAGE_RE.search(cleaned) or _bangs >= 2:
                                            _xsc = _crashout_score(cleaned, hour=dt.hour if dt else None)
                                            # daytime gate; at 2–6am the witching bonus (+1.8) in
                                            # _crashout_score lowers the effective bar (intended)
                                            if _xsc >= 2.0:
                                                crashout_cands.append((round(_xsc, 2), cleaned.strip()))
                                if is_command:
                                    command_invocations += 1
                                proj = os.path.basename(cwd) if cwd else "?"
                                if sid and sid not in seen_session_open:
                                    seen_session_open.add(sid)
                                    opening_prompts.append((dt, proj, cleaned[:600]))
                                longest_prompts.append((len(cleaned), proj, cleaned[:600]))
                                if len(longest_prompts) > 400:
                                    longest_prompts.sort(key=lambda x: -x[0])
                                    del longest_prompts[120:]

                    # ---- tool results inside user turns ---------------------
                    content = msg.get("content")
                    if isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "tool_result":
                                if b.get("is_error"):
                                    tool_errors += 1
                                    if sid:
                                        pending_error[sid] = True

                # ---- assistant turns ---------------------------------------
                elif etype == "assistant" and msg is not None:
                    assistant_turns += 1
                    mdl = msg.get("model")
                    if mdl:
                        model_counter[mdl] += 1
                    if ev.get("attributionSkill"):
                        skill_counter[ev["attributionSkill"]] += 1
                    content = msg.get("content")
                    if isinstance(content, list):
                        for b in content:
                            if not isinstance(b, dict):
                                continue
                            bt = b.get("type")
                            if bt == "text":
                                text_blocks += 1
                            elif bt == "thinking":
                                thinking_blocks += 1
                                thinking_chars += len(b.get("thinking", "") or "")
                            elif bt == "tool_use":
                                name = b.get("name", "?")
                                inp = b.get("input", {}) if isinstance(b.get("input"), dict) else {}
                                tool_use_total += 1
                                tool_counter[name] += 1
                                cat_counter[classify_tool(name)] += 1
                                if name.startswith("mcp__"):
                                    mcp_calls += 1
                                else:
                                    native_calls += 1

                                # a tool use after a pending error = recovery
                                if sid and pending_error.get(sid):
                                    recovered_errors += 1
                                    pending_error[sid] = False

                                if name == "Skill":
                                    s = inp.get("skill")
                                    if s:
                                        skill_counter[s] += 1
                                if name == "Agent":
                                    st = inp.get("subagent_type", "general-purpose")
                                    subagent_counter[st] += 1
                                if name in ASK_TOOLS:
                                    questions_asked += 1
                                if inp.get("run_in_background"):
                                    background_tasks += 1
                                if name in SCHEDULE_TOOLS:
                                    scheduled_actions += 1

                                # ---- code churn + iteration depth ----------
                                if name == "Edit":
                                    a = line_count(inp.get("new_string", ""))
                                    r = line_count(inp.get("old_string", ""))
                                    lines_added += a
                                    lines_removed += r
                                    fpth = inp.get("file_path")
                                    if sid and fpth:
                                        file_edit_run[sid][fpth] += 1
                                elif name == "Write":
                                    a = line_count(inp.get("content", ""))
                                    lines_added += a
                                    fpth = inp.get("file_path")
                                    if sid and fpth:
                                        file_edit_run[sid][fpth] += 1
                                elif name == "MultiEdit":
                                    for e in inp.get("edits", []) or []:
                                        if isinstance(e, dict):
                                            lines_added += line_count(e.get("new_string", ""))
                                            lines_removed += line_count(e.get("old_string", ""))
                                    fpth = inp.get("file_path")
                                    if sid and fpth:
                                        file_edit_run[sid][fpth] += 1
                                elif name == "NotebookEdit":
                                    lines_added += line_count(inp.get("new_source", ""))
                                    fpth = inp.get("notebook_path")
                                    if sid and fpth:
                                        file_edit_run[sid][fpth] += 1
                                elif name == "Bash":
                                    cmd = inp.get("command", "") or ""
                                    if bash_writes_file(cmd):
                                        bash_write_calls += 1
                                        bash_authored_lines += cmd.count("\n")
                                    if bash_runs_tests(cmd):
                                        shell_test_runs += 1
                                    if "git commit" in cmd:
                                        git_commits += 1
                                        # flush iteration-depth run for this session
                                        if sid in file_edit_run:
                                            for cnt in file_edit_run[sid].values():
                                                if cnt > 0:
                                                    edits_per_file_events.append(cnt)
                                            file_edit_run[sid].clear()

        # end of file: flush any remaining edit runs as iteration-depth samples
        for sdict in file_edit_run.values():
            for cnt in sdict.values():
                if cnt > 0:
                    edits_per_file_events.append(cnt)

    # ---- derive ----------------------------------------------------------------
    total_sessions = len(session_ts) or len(session_files)
    # Active time = sum of consecutive inter-event gaps, each capped at GAP_CAP_S,
    # so resumed-session reuse and overnight idle don't inflate engaged time.
    durations_min = []
    longest_burst_s = 0.0
    BURST_GAP_S = 1800               # a gap > 30 min ends a contiguous work "run"
    for ts_list in session_ts.values():
        ts_list.sort()
        active_s = 0.0
        for a, bnext in zip(ts_list, ts_list[1:]):
            active_s += min(bnext - a, GAP_CAP_S)
        durations_min.append(active_s / 60.0)
        # Longest *contiguous* burst (no gap > 30 min). sessionId is reused across
        # resumed sessions, so a single id can span weeks — max(session duration) is
        # meaningless; the longest unbroken burst is the honest "longest run."
        bstart = bprev = None
        for t in ts_list:
            if bprev is None:
                bstart = bprev = t
            elif t - bprev > BURST_GAP_S:
                longest_burst_s = max(longest_burst_s, bprev - bstart)
                bstart = bprev = t
            else:
                bprev = t
        if bstart is not None:
            longest_burst_s = max(longest_burst_s, bprev - bstart)
    active_hours = sum(durations_min) / 60.0
    avg_session_min = statistics.mean(durations_min) if durations_min else 0
    median_session_min = statistics.median(durations_min) if durations_min else 0
    longest_run_min = longest_burst_s / 60.0

    avg_prompt_len = statistics.mean(prompt_lengths) if prompt_lengths else 0
    median_prompt_len = statistics.median(prompt_lengths) if prompt_lengths else 0

    total_churn = lines_added + lines_removed          # tool-authored only (Edit/Write)
    code_velocity = (total_churn / active_hours) if active_hours > 0 else 0

    # Gold-standard churn: real git insertions/deletions, capturing EVERY committed
    # change however it was made (Edit, Bash heredoc, sed, vim...). 100% local.
    gc = git_churn(list(project_activity.keys()),
                   all_min_dt.isoformat() if all_min_dt else "1970-01-01",
                   all_max_dt.isoformat() if all_max_dt else "2100-01-01")
    git_velocity = (gc["churn"] / active_hours) if active_hours > 0 else 0

    explore = cat_counter.get("explore", 0) + thinking_blocks
    produce = cat_counter.get("produce", 0)
    execute = cat_counter.get("execute", 0)
    delegate = cat_counter.get("delegate", 0)
    doing = produce + execute + delegate
    planning_ratio = (explore / doing) if doing else 0

    tool_diversity = len(tool_counter)
    # shannon entropy over tool distribution (bonus, normalized 0-1)
    tot = sum(tool_counter.values()) or 1
    entropy = -sum((c / tot) * math.log2(c / tot) for c in tool_counter.values())
    norm_entropy = entropy / math.log2(tool_diversity) if tool_diversity > 1 else 0

    error_recovery_ratio = (recovered_errors / tool_errors) if tool_errors else 0
    error_rate_per_100_tools = (tool_errors / tool_use_total * 100) if tool_use_total else 0
    _depths = sorted(edits_per_file_events)
    iteration_mean = statistics.mean(_depths) if _depths else 0
    iteration_median = statistics.median(_depths) if _depths else 0
    iteration_p90 = pctile(_depths, 90)
    iteration_max = max(_depths) if _depths else 0
    heavy_files = sum(1 for d in _depths if d > 15)   # files hammered >15x in one session

    actions_per_prompt = (tool_use_total / prompts_count) if prompts_count else 0
    # autonomy proxy 0-100: weighted blend, transparent + bounded
    auto_actions = min(actions_per_prompt / 25.0, 1.0) * 45          # heavy agentic loops
    auto_deleg = min(delegate / max(total_sessions, 1) / 1.5, 1.0) * 20  # subagent dispatch rate
    auto_sched = min((scheduled_actions + background_tasks) / max(total_sessions, 1), 1.0) * 15
    auto_lowq = (1 - min(questions_asked / max(prompts_count, 1) * 6, 1.0)) * 20  # rarely stops to ask
    autonomy_score = round(auto_actions + auto_deleg + auto_sched + auto_lowq, 1)

    span_days = (all_max_dt - all_min_dt).days + 1 if (all_min_dt and all_max_dt) else 0
    active_days = len(date_set)

    DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    tzname = datetime.now().astimezone().tzname()
    tzoffset = datetime.now().astimezone().strftime("%z")

    peak_hours = [h for h, _ in hour_hist.most_common(3)]
    preferred_days = [DOW[d] for d, _ in weekday_hist.most_common(3)]

    stats = {
        "scope": "Sources: " + (", ".join(sorted(source_files)) or "none"),
        "generated_local_only": True,
        "corpus": {
            "sources": {s: {"files": source_files[s], "sessions": len(source_sessions[s]),
                            "prompts": source_prompts[s]} for s in sorted(source_files)},
            "files_parsed": files_parsed,
            "lines_total": lines_total,
            "lines_unparseable": lines_bad,
            "date_range": [all_min_dt.isoformat() if all_min_dt else None,
                            all_max_dt.isoformat() if all_max_dt else None],
            "span_days": span_days,
            "active_days": active_days,
            "timezone": f"{tzname} (UTC{tzoffset[:3]}:{tzoffset[3:]})",
        },
        "volume": {
            "total_sessions": total_sessions,
            "total_prompts": prompts_count,
            "command_invocations": command_invocations,
            "avg_prompt_length_chars": round(avg_prompt_len, 1),
            "median_prompt_length_chars": round(median_prompt_len, 1),
            "assistant_turns": assistant_turns,
            "tool_calls_total": tool_use_total,
            "thinking_blocks": thinking_blocks,
        },
        "tools": {
            "tool_diversity": tool_diversity,
            "tool_entropy_normalized": round(norm_entropy, 3),
            "mcp_calls": mcp_calls,
            "native_calls": native_calls,
            "mcp_share": round(mcp_calls / (mcp_calls + native_calls), 3) if (mcp_calls + native_calls) else 0,
            "top_tools": tool_counter.most_common(15),
            "category_breakdown": dict(cat_counter),
        },
        "velocity": {
            "git_churn_total": gc["churn"],
            "git_insertions": gc["insertions"],
            "git_deletions": gc["deletions"],
            "git_commits_real": gc["commits"],
            "git_velocity_lines_per_hour": round(git_velocity, 1),
            "git_repos_with_commits": gc["repos_with_commits"],
            "git_repos_seen": gc["repos_seen"],
            "git_per_repo": gc["per_repo"],
            "tool_churn_edit_write": total_churn,
            "tool_lines_added": lines_added,
            "tool_lines_removed": lines_removed,
            "tool_velocity_lines_per_hour": round(code_velocity, 1),
            "shell_write_calls": bash_write_calls,
            "shell_authored_lines_est": bash_authored_lines,
            "active_hours": round(active_hours, 1),
            "git_commits_grep": git_commits,
        },
        "behavior": {
            "planning_ratio_explore_to_doing": round(planning_ratio, 2),
            "explore_actions": explore,
            "produce_actions": produce,
            "execute_actions": execute,
            "delegate_actions": delegate,
            "avg_session_minutes": round(avg_session_min, 1),
            "median_session_minutes": round(median_session_min, 1),
            "longest_run_minutes": round(longest_run_min, 1),
            "polite_prompts": polite_prompts,
            "error_recovery_ratio": round(error_recovery_ratio, 3),
            "error_rate_per_100_tools": round(error_rate_per_100_tools, 1),
            "tool_errors": tool_errors,
            "recovered_errors": recovered_errors,
            "api_errors_retries": api_errors,
            "iteration_depth_mean": round(iteration_mean, 2),
            "iteration_depth_median": round(iteration_median, 2),
            "iteration_depth_p90": iteration_p90,
            "iteration_depth_max": iteration_max,
            "files_hammered_over_15x": heavy_files,
            "actions_per_prompt": round(actions_per_prompt, 1),
            "questions_asked": questions_asked,
            "background_tasks": background_tasks,
            "scheduled_actions": scheduled_actions,
            "shell_test_runs": shell_test_runs,
        },
        "rhythm": {
            "hour_histogram_local": {str(h): hour_hist.get(h, 0) for h in range(24)},
            "weekday_histogram": {DOW[d]: weekday_hist.get(d, 0) for d in range(7)},
            "peak_hours_local": peak_hours,
            "preferred_days": preferred_days,
        },
        "stack": {
            "models": model_counter.most_common(),
            "top_skills": skill_counter.most_common(15),
            "subagent_types": subagent_counter.most_common(10),
            "top_projects": [(os.path.basename(p), c, len(project_sessions[p]))
                             for p, c in project_activity.most_common(12)],
        },
        "autonomy": {
            "autonomy_score_0_100": autonomy_score,
            "components": {
                "actions_per_prompt": round(auto_actions, 1),
                "delegation": round(auto_deleg, 1),
                "scheduling_background": round(auto_sched, 1),
                "low_question_rate": round(auto_lowq, 1),
            },
        },
    }

    with open(os.path.join(OUT_DIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, default=str)

    write_report(stats)
    write_narrative_input(stats, opening_prompts, longest_prompts)
    scores = compute_scores(stats)
    archetype, quote = pick_archetype(stats, scores)
    # "In your own words" — pick the go-to phrase (most-repeated short prompt seen in >=2
    # sessions), most cryptic, biggest crash-out. VERBATIM, never stored in stats.json.
    goto = None
    for ph, cnt in phrase_counts.most_common(25):
        if cnt >= 3 and len(phrase_sess.get(ph, ())) >= 2:
            goto = (phrase_repr[ph], cnt, len(phrase_sess[ph]))
            break
    def _dedup_rank(cands):   # keep highest score per unique prompt, ranked (deterministic)
        best = {}
        for sc, tx in cands:
            k = tx.lower()
            if k not in best or sc > best[k][0]:
                best[k] = (sc, tx)
        return sorted(best.values(), key=lambda x: (-x[0], x[1]))   # tie-break on text → reproducible
    cryptic_cands = _dedup_rank(cryptic_cands)
    crashout_cands = _dedup_rank(crashout_cands)
    # Each card shows the SINGLE best quote; a ↻ button rerolls through this small pool
    # (top few within striking distance of #1 — quality only, no weak tail).
    def _quote_pool(cands, n=6, floor=0.5):
        if not cands:
            return []
        top = cands[0][0]
        return [tx for sc, tx in cands if sc >= top * floor][:n]
    rage_pool = _quote_pool([(sc, tx) for sc, tx in crashout_cands if len(tx.split()) <= 9])
    cuff_pool = _quote_pool(cryptic_cands)
    voice = {"goto": goto, "crashouts": rage_pool, "cryptics": cuff_pool}
    write_profile_html(stats, archetype, quote, scores, voice)
    print("\nWrote stats.json, report.md, narrative_input.md, profile.html to", OUT_DIR)
    if "--no-open" not in sys.argv:
        _open_in_browser(os.path.join(OUT_DIR, "profile.html"))
    print(f"  archetype: {archetype}  scores: {scores}")
    print(f"  sources: " + ", ".join(f"{s}({source_files[s]}f/{len(source_sessions[s])}s)"
                                      for s in sorted(source_files)))
    print(f"  sessions={total_sessions}  prompts={prompts_count}  tool_calls={tool_use_total}")
    print(f"  git churn={gc['churn']:,} lines (gold std, {gc['repos_with_commits']}/{gc['repos_seen']} repos)  "
          f"vs tool-only={total_churn:,}  git velocity={git_velocity:.0f} ln/hr")
    print(f"  iteration depth: mean {iteration_mean:.1f} / max {iteration_max} ({heavy_files} files >15x)  "
          f"errors={tool_errors} ({error_rate_per_100_tools:.1f}/100 tools)")
    print(f"  autonomy={autonomy_score}/100  planning_ratio={planning_ratio:.2f}")
    # The only "analytics" a no-telemetry tool gets is what people choose to show: a star or a
    # shared poster. One friendly line — no nag, no second ask (see feedback on content voice).
    print(f"\n  ⭐ Liked your profile? A star helps other builders find paxel: {REPO_URL}")
    print("     (it runs 100% locally and always will — a star is the only thing we can count.)")


if __name__ == "__main__":
    main()
