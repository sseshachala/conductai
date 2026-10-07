"""paxel scoring: split out of the original single-file paxel.py."""

import json


def _clamp(x):
    return max(0.0, min(1.0, x))


def _d10(x):
    """First 10 chars of an ISO date, or '—' when missing (empty/timestampless corpus)."""
    return (x or "")[:10] or "—"


_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _mon_yr(iso):
    """'2025-06-08' -> 'Jun 2025' (human-readable timeframe for the share poster)."""
    iso = iso or ""
    if len(iso) >= 7 and iso[4] == "-":
        try:
            return f"{_MONTHS[int(iso[5:7])]} {iso[0:4]}"
        except (ValueError, IndexError):
            pass
    return (iso[:10] or "—")


def _js(obj):
    """json.dumps for embedding INSIDE a <script> tag. Python's json.dumps does not escape
    '<', '>', '&', so a prompt containing '</script>' (a real web-dev question) would close
    the script element early and break the whole page. Escape them to \\uXXXX (still valid
    JSON/JS), plus the U+2028/U+2029 line separators that break JS string literals."""
    return (json.dumps(obj)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace(" ", "\\u2028").replace(" ", "\\u2029"))


def _skill_uses(stats, needle):
    return sum(n for k, n in stats["stack"].get("top_skills", []) if needle in k.lower())


def _skill_uses_any(stats, needles):
    return sum(n for k, n in stats["stack"].get("top_skills", [])
               if any(nd in k.lower() for nd in needles))


def _evidence(stats):
    """How much activity we actually have to judge habits on, 0..1. ~1.0 for any real
    corpus, near 0 for a thin one. Used to stop 'absence of a signal' from reading as
    'did it perfectly' in the inverse score terms — a barely-used corpus shouldn't grade
    as a flawless builder. (See _ev and the LOW_DATA flag in write_profile_html.)
    Saturates at ~2000 tool calls (≈15 real sessions) so the gating actually has a
    gradient across thin→mid corpora, not just sub-30-minute ones."""
    return _clamp(stats["volume"]["tool_calls_total"] / 2000)


def _ev(credit, ev):
    """Pull an ABSENCE-reward score term toward a neutral 0.5 when evidence (ev) is low,
    so 'no data' lands at the midpoint (admitted uncertainty) instead of a flattering 1.0.
    At ev=1.0 (any real corpus) this returns `credit` unchanged — a true no-op for real
    users; it only ever bites thin corpora. Apply ONLY to inverse terms (those that score
    high when a 'bad' metric is low/zero); presence terms already score 0 for 'didn't do it'."""
    return 0.5 * (1 - ev) + ev * credit


def compute_scores(stats):
    # THREE graded axes (Execution/Planning/Engineering), grounded in gstack (module note
    # above) and then hardened by a gstack self-audit. Steering is NOT scored here — it's
    # described in steering_reading (it was inverted; see that function). Design rules:
    #   1. Each metric is owned by EXACTLY ONE place — no metric drives two graded axes, so
    #      the axes are genuinely independent (no hidden correlation).
    #   2. actions_per_prompt and questions_asked live ONLY in steering_reading (hands-on
    #      cadence — described, not scored); neither graded axis rewards them.
    #   3. iteration_depth_p90 lives ONLY in Engineering.
    #   4. Skill-detection terms are kept but de-weighted (a builder who plans in Notion
    #      and reviews on GitHub shouldn't score 0) — behavior carries the axes.
    # Weights sum to 1.0 per axis; every term is clamped 0..1 against a justified target;
    # `_ev` pulls the INVERSE terms toward neutral on a thin corpus.
    v, b, vel = stats["volume"], stats["behavior"], stats["velocity"]
    if v["total_sessions"] == 0 or v["tool_calls_total"] == 0:
        # No real activity → don't manufacture a flattering "Quality Guardian 9.0"
        return {"Execution": 0.0, "Planning": 0.0, "Engineering": 0.0}
    sess = max(v["total_sessions"], 1)
    prompts = max(v["total_prompts"], 1)
    hours = max(vel["active_hours"], 0.1)
    ev = _evidence(stats)   # 0..1 confidence; gates the inverse terms so a thin corpus
                            # can't read as flawless (no-op at ev=1.0 for any real user).

    # EXECUTION — shipped output at AI leverage. Three signals, no overlap with other axes:
    #   (a) RATE: gold-standard git churn per active hour (coverage-corrected — git often
    #       sees only some repos; we nudge ≤1.4× by coverage rather than penalize, and the
    #       report discloses it). (b) FIDELITY: how much of what you GENERATED actually got
    #       committed — git churn vs tool churn — the audit's headline "are you shipping or
    #       just exploring" signal (also coverage-corrected). (c) DELEGATION/parallelism.
    #   Dropped vs the old version: actions_per_prompt (now in steering_reading, described
    #   not scored) and raw session length (the audit called it noise — a long distracted
    #   session isn't execution).
    git_cov = max(vel["git_repos_with_commits"] / max(vel["git_repos_seen"], 1), 0.7)
    eff_git_churn = vel["git_churn_total"] / git_cov
    fidelity = eff_git_churn / max(vel["tool_churn_edit_write"], 1)
    execution = 10 * (
        0.40 * _clamp((eff_git_churn / hours) / 400)                      # committed-code rate, coverage-corrected
        + 0.25 * _clamp(fidelity / 0.5)                                   # ship-vs-generate fidelity (committed / generated)
        + 0.35 * _clamp((b["delegate_actions"] + b["background_tasks"]) / max(prompts * 0.3, 1)))  # delegation/parallelism

    # PLANNING — think before you build. Behavior-led.
    # DROPPED the avg_prompt_length term (was 0.25): it is experience-INVERTING — expertise
    # produces TERSER, more precise prompts, so the term paid for verbosity. It's the main reason a
    # 4-month vibe-coder maxed Planning over a 30-year engineer (an expert-elicitation validity
    # review caught this). Weight redistributed to the construct-relevant terms.
    plan_skills = _skill_uses_any(stats, ("brainstorm", "writing-plan", "plan", "spec",
                                          "office-hours", "autoplan", "grill", "ceo-review",
                                          "eng-review", "design-review"))
    planning = 10 * (
        0.45 * _clamp(b["planning_ratio_explore_to_doing"] / 0.65)        # explore-before-build (behavioral)
        + 0.30 * _clamp((v["thinking_blocks"] / sess) / 12.0)           # reasoning depth per session
        + 0.25 * _clamp((plan_skills / sess) / 0.8))                     # plan/spec ceremony (toolchain-biased → kept lowest)

    # STEERING IS NOT SCORED — it's DESCRIBED (see steering_reading). Hands-on cadence
    # (actions/prompt + how often the agent checks in) is real and measurable, but it has no
    # good/bad end: a deliberate hands-off operator who delegates and gets clean autonomous output
    # back is steering by a mechanism we CANNOT read from transcripts (it needs delegation→
    # survived-to-commit attribution). Grading it INVERTED the axis — `(15 - actions_per_prompt)`
    # meant a more autonomous engineer scored LOWER (the Chris Sells case). You don't fix a
    # backwards gauge with a disclaimer underneath it; you stop grading it and state the fact.
    # (An earlier "autonomous command" term that tried to credit delegation×low-error was also
    # reverted — it collapsed to error-rate-in-a-costume; see git history.)

    # ENGINEERING — craft / low rework. The old churn_back term (deletion ratio) was CUT:
    # it scored a clean refactor as "thrash" and gave a perfect score to anyone who never
    # committed. Replaced by iteration_depth_mean ("did you get the file right early"), the
    # honest rework signal. p90 + file-hammering stay here (their only home). Ceremony de-weighted.
    # "code-review" (not bare "review") so this doesn't greedily match Planning's
    # plan-eng-review / plan-design-review / ceo-review ceremonies (which live in plan_skills).
    eng_skills = _skill_uses_any(stats, ("code-review", "test", "tdd", "qa", "investigate",
                                         "retro", "learn", "cso", "karpathy", "debug")) \
        + b.get("shell_test_runs", 0)   # CLI tests (pytest/go test/…) count as quality work too
    engineering = 10 * (
        0.30 * _ev(1 - _clamp((b["iteration_depth_mean"] - 2) / 8), ev)  # low rework: got files right early
        + 0.25 * _ev(1 - _clamp((b["iteration_depth_p90"] - 3) / 9), ev)  # clean iteration: low typical depth
        + 0.20 * _ev(1 - _clamp((b["files_hammered_over_15x"] / sess) / 0.25), ev)  # focused: few hammered files
        + 0.15 * _clamp((eng_skills / sess) / 3.0)                       # quality ceremonies: review/qa/investigate
        + 0.10 * _ev(1 - _clamp(b["error_rate_per_100_tools"] / 10), ev))  # low error rate: root-cause discipline

    return {"Execution": round(execution, 1), "Planning": round(planning, 1),
            "Engineering": round(engineering, 1)}


def steering_reading(stats):
    """Steering is DESCRIBED, not graded (see compute_scores for why). We report how you run
    agents — long leash vs short leash — as a fact, with no implied good/bad. Returns a short
    label + a one-line detail, both safe to render and to share (numbers only, no prompt text)."""
    v, b = stats["volume"], stats["behavior"]
    prompts = max(v["total_prompts"], 1)
    apr = b["actions_per_prompt"]               # tool actions between your prompts
    qrate = b["questions_asked"] / prompts      # how often the agent stopped to check in
    if apr >= 12:
        label, gloss = "Long leash", "you point the agent and let it run"
    elif apr >= 6:
        label, gloss = "Medium leash", "autonomous stretches, hands-on steering"
    else:
        label, gloss = "Short leash", "you stay close and course-correct often"
    detail = (f'~{apr:.0f} actions per turn before you weigh in · '
              f'the agent checked in on {qrate*100:.0f}% of your prompts')
    return {"label": label, "gloss": gloss, "detail": detail}


def pick_archetype(stats, scores):
    b, vel = stats["behavior"], stats["velocity"]
    # brute = a HABITUAL grinder (high typical iteration), not one 40-edit outlier session
    brute = b["iteration_depth_p90"] >= 12 or (vel["shell_authored_lines_est"] > 50000
                                               and b["error_rate_per_100_tools"] >= 3)
    plan_hi = scores.get("Planning", 0) >= 7.5
    exec_hi = scores.get("Execution", 0) >= 8
    eng_hi = scores.get("Engineering", 0) >= 7.5
    # Steering isn't scored anymore — read hands-on directly from cadence (short leash).
    # "The Director" stays a positive, descriptive identity; there's no inverse-shaming pole.
    steer_hi = b["actions_per_prompt"] <= 6
    # when both Execution and Engineering qualify, let the dominant one win the label
    exec_hi = exec_hi and scores.get("Execution", 0) >= scores.get("Engineering", 0)
    if plan_hi and brute:
        name, q = "Brute-Force Architect", "You plan and scaffold like an architect — then grind the hard parts by hand, in the shell, until they work."
    elif plan_hi:
        name, q = "The Architect", "You plan first, codify your decisions, and build scaffolding that compounds."
    elif exec_hi and brute:
        name, q = "The Bulldozer", "You point yourself at the problem and push through it until it gives."
    elif exec_hi:
        name, q = "Velocity Machine", "You move fast, delegate hard, and keep a lot of plates spinning at once."
    elif eng_hi:
        name, q = "Quality Guardian", "You keep churn low and the bar high — measured changes, reviewed twice."
    elif steer_hi:
        name, q = "The Director", "You stay in the loop — short chains, frequent check-ins, no runaway agents."
    else:
        # No single mode dominates. (Time-of-day isn't a build style — it's a 'what we
        # noticed' card, not an identity — so Night Owl was retired as an archetype.)
        name, q = "The Builder", "Balanced and pragmatic — no single mode dominates; you adapt to the problem in front of you."
    return name, q


def signature_moves(stats):
    """Named decision-patterns ('signature moves') drawn from real session behavior,
    each tagged with the gstack sprint stage it expresses. Only moves whose gate
    actually fires are returned (we never pad) — top 5 by a comparable 0..1 strength.
    Cites measured numbers, NEVER raw prompt text, so the profile stays shareable
    without leaking session content. NOTE for maintainers: evidence HTML is trusted /
    safe-by-construction — never interpolate user/transcript-derived strings (skill,
    project, tool names) here without html.escape; today every value is a number or a
    static template (the lone tool-name use is gated to == "Bash" and emits a literal)."""
    v, b, vel, t, st = (stats["volume"], stats["behavior"], stats["velocity"],
                        stats["tools"], stats["stack"])
    sess = max(v["total_sessions"], 1)
    prompts = max(v["total_prompts"], 1)

    def sk(*needles):
        return sum(n for k, n in st.get("top_skills", []) if any(nd in k.lower() for nd in needles))

    top_tool = (str(t["top_tools"][0][0]) if t["top_tools"] else "")
    deleg = b["delegate_actions"] + b["background_tasks"]
    pool = []   # (strength 0..1, gstack-tag, title, evidence_html)

    rev = sk("review", "code-review")
    if rev >= 50 and rev >= sess * 0.5:
        pool.append((_clamp(rev / (sess * 2)), "Review",
            "You review more than you write",
            f'<b>{rev:,}</b> code-review passes — one of your most-used skills. '
            f'You don\'t trust a diff until a second set of eyes has seen it.'))

    if b["planning_ratio_explore_to_doing"] >= 0.55 and b["iteration_depth_max"] >= 40:
        pool.append((_clamp(b["iteration_depth_max"] / 100.0), "Think → Build",
            "Plan wide, then grind narrow",
            f'A <b>{b["planning_ratio_explore_to_doing"]:.2f}</b> explore-to-build ratio — you read and '
            f'search far more than you type — yet you\'ll hammer one file <b>{b["iteration_depth_max"]}×</b> '
            f'rather than re-architect. Blueprint, then bulldozer.'))

    if deleg >= 100 and deleg >= prompts * 0.3:
        shell = " with the shell as your top tool" if top_tool == "Bash" else ""
        pool.append((_clamp(deleg / (prompts * 0.8)), "Build",
            "You run a team, not a tool",
            f'<b>{deleg:,}</b> delegated &amp; backgrounded agent runs{shell}. '
            f'You parallelize and grind rather than babysit one chat.'))

    tb = v["thinking_blocks"]
    if tb / sess >= 8:
        pool.append((_clamp((tb / sess) / 30.0), "Think",
            "You think before you touch the diff",
            f'<b>{tb:,}</b> reasoning blocks (~{tb // sess}/session) before edits land — '
            f'you deliberate hard, then commit.'))

    plan = sk("brainstorm", "writing-plan", "autoplan", "spec")
    if plan >= 30 and plan >= sess * 0.35:
        pool.append((_clamp(plan / float(sess)), "Plan",
            "You write the plan before the code",
            f'<b>{plan:,}</b> planning &amp; brainstorming runs — you scaffold the decision '
            f'before the implementation, gstack-style.'))

    qrate = b["questions_asked"] / prompts
    if qrate < 0.03 and prompts > 200:
        pool.append((0.45, "User Sovereignty",
            "You direct, you don't deliberate",
            f'The agent stopped to ask you on just <b>{qrate*100:.0f}%</b> of {prompts:,} prompts — '
            f'you point it and let it run, rather than getting pulled into a back-and-forth.'))

    if vel["shell_authored_lines_est"] >= 20000 and top_tool == "Bash":
        pool.append((_clamp(vel["shell_authored_lines_est"] / 80000.0), "Build",
            "You live in the shell",
            f'~<b>{vel["shell_authored_lines_est"]:,}</b> lines authored through Bash heredocs and '
            f'redirects — real work most profilers never even see.'))

    pool.sort(key=lambda x: -x[0])
    return [(tag, title, ev) for _, tag, title, ev in pool[:5]]


def growth_edges(stats, scores):
    """Specific next-steps keyed off the user's OWN weakest signals — not generic advice.
    Each leads with a PRACTICE the reader can adopt today, then names the gstack skill
    that embodies it (in parens) as an optional, installable upgrade — so the advice is
    actionable whether or not they run gstack. Only gated edges are returned; top 3,
    most-urgent first. NOTE for maintainers: advice HTML is trusted/safe-by-construction
    — never interpolate user/transcript-derived strings (skill, project, tool names)
    here without html.escape; today every interpolated value is a number or static."""
    v, b, vel, st = (stats["volume"], stats["behavior"], stats["velocity"], stats["stack"])
    sess = max(v["total_sessions"], 1)
    prompts = max(v["total_prompts"], 1)

    def sk(*needles):
        return sum(n for k, n in st.get("top_skills", []) if any(nd in k.lower() for nd in needles))

    rev = sk("review", "code-review")
    tdd = sk("test", "tdd", "qa") + b.get("shell_test_runs", 0)   # named test skills + CLI test runs
    err = b["error_rate_per_100_tools"]
    pool = []   # (priority: lower = more urgent / shows first, eyebrow, title, advice_html)

    # NO steering edge: hands-on cadence has no good/bad end (it's described, not scored — see
    # steering_reading), so telling an autonomous operator to "steer harder" is exactly the
    # inversion we removed. We don't advise people to babysit clean autonomous runs.

    # Only fires when we genuinely see few tests — and it SAYS what it can and can't detect, so a
    # CLI tester is never told "0 test runs" as though it were fact.
    if rev >= 50 and tdd < max(rev * 0.1, 5):
        pool.append((1.5, "Add a reflex",
            "Pair your review reflex with a test reflex",
            f'We spotted <b>{rev:,}</b> code-reviews but only <b>{tdd}</b> test runs — counting named test '
            f'skills <i>and</i> shell runners like <code>pytest</code> / <code>go test</code> / '
            f'<code>npm test</code>. If you test some other way we can\'t see, skip this. If tests really '
            f'are thin, make the double-check a <i>regression test</i>: one for every bug you fix. '
            f'(gstack\'s <code>/qa</code> does this.)'))

    # High iteration is only "whack-a-mole" if it's THRASH — so we require an elevated error rate
    # alongside it. A clean deep-iterator (low errors) is doing deliberate work, not flailing, and
    # is left alone (this also spares agent-driven iteration, which tends to keep errors low).
    if (b["iteration_depth_max"] >= 40 or b["files_hammered_over_15x"] >= 10) and err >= 5:
        pool.append((2.0, "Stop the grind",
            "When a file fights back, root-cause it",
            f'<b>{b["iteration_depth_max"]}×</b> on one file and <b>{b["files_hammered_over_15x"]}</b> files '
            f'past 15 edits, next to ~<b>{err}</b> errors per 100 tool calls — that pairing reads as '
            f'retry-thrash more than deliberate iteration. When a file resists past ~15 tries, find the root '
            f'cause before the next edit. (gstack names this <code>/investigate</code>.)'))

    if scores.get("Planning", 10) < 6:
        pool.append((scores.get("Planning", 10), "Plan first",
            "Spend more time in Think + Plan",
            f'Planning is <b>{scores.get("Planning")}</b>. Sketch the plan and reframe the ask <i>before</i> '
            f'writing code — it\'s the cheapest place to catch a wrong turn. '
            f'(gstack front-loads this with <code>/office-hours</code> + <code>/autoplan</code>.)'))

    eng_skills = sk("review", "qa", "investigate", "retro")
    if scores.get("Engineering", 10) < 6 and eng_skills < sess * 0.3:
        pool.append((scores.get("Engineering", 10) + 0.1, "Boil the lake",
            "Run a quality pass before you ship",
            f'Engineering is <b>{scores.get("Engineering")}</b>. Add one deliberate review-and-test pass on '
            f'every branch before you ship — that\'s where craft compounds. '
            f'(gstack\'s back half: <code>/review</code>, <code>/qa</code>, <code>/investigate</code>, <code>/retro</code>.)'))

    if not pool:
        worst = min(scores, key=scores.get) if scores else ""
        wv = scores.get(worst, 10)
        if worst and wv < 6.5:
            # Nothing specific fired, but an axis IS low — don't claim "balanced" when the scorecard
            # shows otherwise. Point at the softest axis honestly instead.
            pool.append((8.5, "Closest to an edge", f'Your softest axis is {worst}',
                f'Nothing jumped out as a single clear next-step, but <b>{worst}</b> at <b>{wv}</b> is your '
                f'lowest axis — the cheapest place to gain. See how {worst} is scored above and lean there.'))
        else:
            pool.append((9.0, "Go deeper",
                "You're balanced — your edge is depth",
                'You\'re even across the build sprint, so the next gear isn\'t a weak spot to patch — it\'s depth. '
                'Add a short retro after each session and let the learnings compound session over session. '
                '(gstack names this <code>/retro</code> — the Reflect stage.)'))

    pool.sort(key=lambda x: x[0])
    return [(eb, title, adv) for _, eb, title, adv in pool[:3]]
