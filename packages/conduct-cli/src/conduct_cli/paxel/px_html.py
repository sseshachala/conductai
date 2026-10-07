"""paxel html: split out of the original single-file paxel.py."""

import os
import re

from px_base import OUT_DIR, _safe_quote
from px_report import REPO_URL, SCORE_NOTES, SCORE_NOTES_SHORT
from px_scoring import _d10, _evidence, _js, _mon_yr, growth_edges, signature_moves, steering_reading


def _pretty_model(m):
    # "claude-opus-4-7" -> "Opus 4.7"; "claude-3-5-sonnet-20241022" -> "Sonnet 3.5"
    m = re.sub(r"^claude-", "", m or "")
    m = re.sub(r"-\d{6,}$", "", m)              # drop trailing date
    parts = [p for p in m.split("-") if p]
    words = [p for p in parts if not p.isdigit()]
    nums = [p for p in parts if p.isdigit()]
    name = (words[0].upper() if words and len(words[0]) <= 3 else
            words[0].capitalize()) if words else (m or "?")
    ver = ".".join(nums[:2])
    return f"{name} {ver}".strip() if ver else name


def _img_data_uri(path):
    try:
        import base64
        with open(path, "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode()
    except Exception:
        return ""


_PROFILE_CSS = """<style>
  :root{--slate:#313941;--beak:#ED7379;--beak-deep:#D14E57;--bg:#eef1f3;--panel:#fff;
    --line:#d9dee2;--text:#16191d;--muted:#5e6a73;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --display:"Josefin Sans","Futura","Century Gothic","Trebuchet MS",sans-serif;
    --serif:"Merriweather",Georgia,"Times New Roman",serif;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);line-height:1.5;-webkit-font-smoothing:antialiased}
  #report{background:var(--bg)} .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  a{color:var(--slate);text-decoration:none} a:hover{text-decoration:underline}
  .wrap{max-width:900px;margin:0 auto;padding:0 22px 70px}
  .topbar{background:var(--panel);border-bottom:1px solid var(--line);padding:13px 0}
  .topbar .wrap{display:flex;align-items:center;gap:12px;padding:0}
  .brandlink{display:flex;align-items:center;gap:12px;color:var(--text)} .brandlink:hover{text-decoration:none;color:var(--beak-deep)}
  .chip{width:40px;height:40px;flex:0 0 auto;background:#fff;border:1px solid var(--line);border-radius:9px;display:flex;align-items:center;justify-content:center}
  .chip img{width:32px;height:32px;object-fit:contain}
  .brand{font-family:var(--display);font-weight:700;font-size:20px;letter-spacing:.05em} .brand .dim{opacity:.6;font-weight:600;font-size:15px}
  .badge{margin-left:auto;font-size:12px;font-weight:600;color:var(--slate);background:#e8edf0;padding:5px 11px;border-radius:999px;border:1px solid var(--line)}
  .hero{padding:54px 0 30px} .eyebrow{color:var(--muted);font-size:14px;margin:0 0 16px}
  .hero h1{font-family:var(--serif);font-size:50px;line-height:1.06;margin:0 0 8px;font-weight:700;letter-spacing:-.01em} .hero h1 .accent{color:var(--beak)}
  .hero .quote{font-family:var(--serif);font-size:19px;font-style:italic;color:#3b444b;margin:18px 0 0;max-width:660px;line-height:1.55}
  .hero .sub{color:var(--muted);margin-top:18px;font-size:15px;max-width:680px} .hero .sub b{color:var(--text)}
  .stat-strip{display:flex;flex-wrap:wrap;gap:24px;margin-top:28px;padding-top:24px;border-top:1px solid var(--line)}
  .stat-strip div{display:flex;flex-direction:column} .stat-strip .n{font-family:var(--serif);font-size:25px;font-weight:700} .stat-strip .l{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
  .share{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:34px} .share .lbl{font-size:13px;color:var(--muted)}
  .btn{display:inline-flex;align-items:center;gap:8px;padding:9px 15px;border-radius:999px;cursor:pointer;font-weight:600;font-size:14px;color:#fff;border:1px solid transparent;font-family:var(--sans)}
  .btn:hover{text-decoration:none;opacity:.9} .btn.x{background:#000} .btn.ghost{background:#fff;color:var(--slate);border-color:var(--line)}
  .btn svg{width:15px;height:15px} .btn.x svg{fill:#fff}
  h2.section{font-family:var(--display);font-size:15px;text-transform:uppercase;letter-spacing:.18em;color:var(--slate);margin:60px 0 14px;font-weight:700}
  p.lead{color:var(--muted);font-size:14.5px;margin:-4px 0 20px;max-width:700px;line-height:1.55}
  .card code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;background:#eef1f3;color:var(--beak-deep);padding:1px 5px;border-radius:4px}
  .disclaimer{background:#fff;border:1px solid var(--line);border-left:4px solid var(--beak);border-radius:6px;padding:14px 16px;margin:-6px 0 24px;font-size:13.5px;color:#48535b;line-height:1.55} .disclaimer b{color:var(--text)}
  .score{display:grid;grid-template-columns:160px 1fr 46px;align-items:center;gap:14px;margin:0 0 14px} .score .name{font-weight:600;font-size:15px}
  .score .track{display:block;height:12px;background:#dde2e6;border-radius:999px;overflow:hidden} .score .fill{display:block;height:100%;min-width:8px;background:linear-gradient(90deg,var(--beak-deep),var(--beak));border-radius:999px}
  .score .val{font-weight:800;text-align:right} .score .note{grid-column:1/-1;color:var(--muted);font-size:13px;margin:-6px 0 4px;padding-left:174px}
  @media(max-width:560px){.score .note{padding-left:0}}
  .steerread{display:grid;grid-template-columns:160px 1fr;align-items:baseline;gap:14px;margin:4px 0 6px;padding-top:14px;border-top:1px solid var(--line)} .steerread .sr-k{font-weight:600;font-size:15px}
  .steerread .sr-v{font-size:15px;color:#48535b} .steerread .sr-v b{color:var(--beak-deep);font-weight:700} .steerread .sr-d{grid-column:2;color:var(--muted);font-size:13px;margin-top:2px}
  @media(max-width:560px){.steerread{grid-template-columns:1fr}.steerread .sr-d{grid-column:1}}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:14px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px 18px 16px;box-shadow:0 1px 2px rgba(20,30,40,.04)} .card.flag{border-left:4px solid var(--beak)}
  .card .q{color:var(--beak-deep);font-size:12.5px;font-weight:700;margin:0 0 8px;text-transform:uppercase;letter-spacing:.03em}
  .card .reroll{font-family:var(--sans);text-transform:none;letter-spacing:0;font-size:11px;font-weight:600;color:var(--beak-deep);background:none;border:1px solid var(--line);border-radius:999px;padding:1px 8px;margin-left:8px;cursor:pointer;vertical-align:middle}
  .card .reroll:hover{background:#fff;border-color:var(--beak)}
  .card .a{font-family:var(--serif);font-size:19px;font-weight:700;margin:0 0 6px} .card .d{color:var(--muted);font-size:13.5px;margin:0}
  footer{margin-top:54px;padding-top:22px;border-top:1px solid var(--line);color:var(--muted);font-size:13px;line-height:1.7} footer .lock{color:var(--beak-deep);font-weight:700} footer .by{color:var(--text)}
</style>"""


def _plain(s):
    """Flatten the trusted <b>/<i>/<code> markup (and the few HTML entities we emit) out of
    a card string so it can be drawn as plain text on the canvas poster. Inputs are
    safe-by-construction (numbers / static templates — see _card)."""
    s = re.sub(r"<[^>]+>", "", s or "")
    for a, b in (("&amp;", "&"), ("&rsquo;", "’"), ("&lsquo;", "‘"),
                 ("&ldquo;", "“"), ("&rdquo;", "”"), ("&mdash;", "—")):
        s = s.replace(a, b)
    return s


def _card(q, a, d, flag=False):
    # q/a/d are injected RAW (no escaping) so callers can use intentional <b>/<code>/<i>
    # markup. Every caller must pass safe-by-construction strings: numbers, static
    # templates, or html.escape()'d values — NEVER raw user/transcript-derived text.
    cls = "card flag" if flag else "card"
    return f'<div class="{cls}"><p class="q">{q}</p><p class="a">{a}</p><p class="d">{d}</p></div>'


def _hero_lead(archetype):
    """The HTML hero says "You're a {archetype}" — but the "The …" archetypes (The Architect/
    Director/Builder/Bulldozer) would read "You're a The Architect". Drop the article for those.
    The archetype string itself is never altered, so the poster keeps its "The Architect." title.
    (No archetype starts with a vowel, so "a" is always right for the rest.)"""
    return "You're" if (archetype or "")[:4].lower() == "the " else "You're a"


def write_profile_html(stats, archetype, quote, scores, voice=None):
    import html as _h
    v, vel, b, r, t, st, c = (stats["volume"], stats["velocity"], stats["behavior"],
                              stats["rhythm"], stats["tools"], stats["stack"], stats["corpus"])
    logo = _img_data_uri(os.path.join(OUT_DIR, "tern.png"))
    chip = f'<span class="chip"><img src="{logo}" alt="Roadmap tern"></span>' if logo else ""

    peak = (r["peak_hours_local"] or [12])[0]
    tod = ("Night owl" if (peak >= 22 or peak <= 4) else "Morning person" if peak <= 11
           else "Afternoon" if peak <= 16 else "Evening")
    wd = r["weekday_histogram"]
    wknd = wd.get("Sat", 0) + wd.get("Sun", 0)
    wkday_avg = sum(wd.get(d, 0) for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]) / 5 or 1
    weekend_a = "No days off" if wknd / 2 >= wkday_avg * 0.6 else "Weekday warrior"
    models = st.get("models", [])
    mtot = sum(n for _, n in models) or 1
    model_a = _h.escape(" → ".join(_pretty_model(m) for m, _ in models[:2]) or "—")
    model_d = _h.escape((", ".join(f"{_pretty_model(m)} {round(n/mtot*100)}%" for m, n in models[:2]) + " of turns.") if models else "—")
    top_tool = (t["top_tools"][0] if t["top_tools"] else ["—", 0])
    top_tool_name = _h.escape(str(top_tool[0]))
    sess = max(v["total_sessions"], 1)
    prompts = max(v["total_prompts"], 1)
    per_sess = round(b["delegate_actions"] / sess, 1)
    git_pct = f'{vel["git_repos_with_commits"]}/{vel["git_repos_seen"]}'

    # The coral left-bar (flag=True) means exactly one thing: "this is an action item."
    # It is used ONLY on the Growth-edge cards. Signature-move and What-we-noticed cards
    # are descriptive, so they stay plain — no flags here.
    h12 = f'{(peak - 1) % 12 + 1}{"am" if peak < 12 else "pm"}'   # 17 -> "5pm", 0 -> "12am"
    _DAYFULL = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday",
                "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
    busy_day = _DAYFULL.get((r["preferred_days"] or ["—"])[0], (r["preferred_days"] or ["—"])[0])
    weekend_d = (f'Your busiest day is {busy_day} — and you logged time most days, weekends included.'
                 if weekend_a == "No days off" else f'Your busiest day is {busy_day}; weekends stay quiet.')
    two_gears = v["avg_prompt_length_chars"] > v["median_prompt_length_chars"] * 2
    prompt_a = "Short, with the odd essay" if two_gears else "Consistent length"
    prompt_d = (f'Half run under {v["median_prompt_length_chars"]:,.0f} characters — quick commands — '
                f'but the average is {v["avg_prompt_length_chars"]:,.0f}.' if two_gears else
                f'Median {v["median_prompt_length_chars"]:,.0f} characters, average {v["avg_prompt_length_chars"]:,.0f} — pretty steady.')
    polite_n = b.get("polite_prompts", 0)
    polite_rate = polite_n / prompts
    polite_a = ("You say thanks a lot" if polite_rate >= 0.12 else
                "Polite enough" if polite_rate >= 0.04 else "All business")
    polite_d = (f'You said please or thank-you in <b>{polite_n:,}</b> of your {v["total_prompts"]:,} prompts '
                f'({polite_rate*100:.0f}%).' + (" When the robots take over, they'll remember."
                                                if polite_rate >= 0.12 else ""))
    lr = b.get("longest_run_minutes", 0)
    lr_h, lr_m = int(lr // 60), int(lr % 60)
    longrun_a = f'{lr_h}h {lr_m}m' if lr_h else f'{lr_m}m'
    qrate_c = b["questions_asked"] / prompts
    teammate = polite_rate >= 0.05 or qrate_c >= 0.04
    agent_a = "Like a teammate" if teammate else "Like a tool"
    agent_d = ('You bounce ideas off it and ask for pushback — more collaborator than command line.'
               if teammate else 'You hand it work and check the result — more command line than collaborator.')
    # "What we noticed" — question-framed eyebrows + plain second-person copy (no jargon).
    cards = [
        _card("How much did you ship?", "Depends how you count",
              f'Edit/Write touched <b>{vel["tool_churn_edit_write"]:,}</b> lines and the shell ~{vel["shell_authored_lines_est"]:,} '
              f'more — but only <b>{vel["git_churn_total"]:,}</b> actually landed in committed git history. '
              f'That committed number is the honest one.'),
        _card("How hard do you grind?", f'{b["iteration_depth_max"]}× on one file',
              f'Your deepest single-file grind in one session — and {b["files_hammered_over_15x"]} files went past 15 edits. '
              f'Your typical file, though? About {b["iteration_depth_mean"]:.1f}.'),
        _card("How often do things break?", f'{b["tool_errors"]:,} errors, {round(b["error_recovery_ratio"]*100)}% recovered',
              f'Roughly {b["error_rate_per_100_tools"]} per 100 tool calls — and you kept going after almost all of them.'),
        _card("Which model do you reach for?", model_a, model_d),
        _card("When do you do your best work?", tod, f'You do your heaviest work around {h12}.'),
        _card("Do you take weekends off?", weekend_a, weekend_d),
        _card("How long are your prompts?", prompt_a, prompt_d),
        _card("How many agents do you run?", f'{b["delegate_actions"]:,} subagents',
              f'About {per_sess} per session, plus {b["background_tasks"]:,} background tasks and {b["scheduled_actions"]} scheduled runs.'),
        _card("How do you see your agent?", agent_a, agent_d),
        _card("How polite are you to it?", polite_a, polite_d),
        _card("What's your longest run?", longrun_a,
              'Your longest unbroken stretch of active work in a single session.'),
        _card("What's your go-to tool?", top_tool_name, f'{top_tool[1]:,} calls — more than any other tool.'),
    ]

    score_rows = "".join(
        f'<div class="score"><span class="name">{name}</span>'
        f'<span class="track"><span class="fill" style="width:{val*10:.0f}%"></span></span>'
        f'<span class="val mono">{val}</span>'
        + (f'<span class="note">{_h.escape(SCORE_NOTES[name])}</span>' if name in SCORE_NOTES else "")
        + '</div>'
        for name, val in scores.items())

    moves = signature_moves(stats)
    edges = growth_edges(stats, scores)
    steer_read = steering_reading(stats)   # Steering is described here, not scored
    moves_html = "".join(_card(tag, title, ev) for tag, title, ev in moves)
    edges_html = "".join(_card(eb, title, adv, flag=True) for eb, title, adv in edges)

    # Data for the canvas-drawn share POSTER (one tall 1200px-wide PNG, drawn at download
    # time so there's no foreignObject → no canvas taint → it works in every browser).
    # Carries: archetype + tagline + timeframe, the scorecard (with one-line notes) paired
    # with the headline numbers, and the curated insight/quote cards. SUBSTANCE FIRST: the
    # signature move + insights lead; the two quote cards (funny, low-substance) come LAST.
    # Quotes are routed through _safe_quote, and the off-the-cuff card is re-read LIVE from
    # the page (#q-cuff) at click time, so a reroll is honored and the user is the gate.
    _voc = voice or {}
    poster_cards = []
    if moves:
        _mtag, _mtitle, _mev = moves[0]
        poster_cards.append({"mode": "insight", "eyebrow": _plain(_mtag),
                             "headline": _plain(_mtitle), "sub": _plain(_mev)})
    if b["delegate_actions"] > 0:
        poster_cards.append({"mode": "insight", "eyebrow": "How many agents?",
                             "headline": f'{b["delegate_actions"]:,} subagents',
                             "sub": f'About {per_sess} per session, plus {b["background_tasks"]:,} '
                                    f'background tasks and {b["scheduled_actions"]} scheduled runs.'})
    poster_cards += [
        {"mode": "insight", "eyebrow": "Best work?", "headline": tod,
         "sub": f"Heaviest work around {h12}."},
        {"mode": "insight", "eyebrow": "Weekends?", "headline": weekend_a, "sub": _plain(weekend_d)},
        {"mode": "insight", "eyebrow": "Your agent is…", "headline": agent_a, "sub": _plain(agent_d)},
        {"mode": "insight", "eyebrow": "Polite to it?", "headline": polite_a, "sub": _plain(polite_d)},
    ]
    if _voc.get("goto") and _safe_quote(_voc["goto"][0]):
        _ph, _cnt, _ns = _voc["goto"]
        poster_cards.append({"mode": "quote", "eyebrow": "Go-to prompt",
                             "headline": _ph, "sub": f"Most-repeated — {_cnt:,}×."})
    if _voc.get("cryptics"):
        poster_cards.append({"mode": "quote", "eyebrow": "Off the cuff", "live": "cuff",
                             "headline": _voc["cryptics"][0], "sub": "Straight from the keyboard."})

    _tag = quote.strip()
    if _tag:
        _tag = _tag[0].upper() + _tag[1:]
        if _tag[-1] not in ".!?":
            _tag += "."
    _dr = c["date_range"] or ["", ""]
    # timeframe + sessions only — prompts/tool-calls already live in "By the numbers".
    _context = f'{_mon_yr(_dr[0])} → {_mon_yr(_dr[1])}  ·  {v["total_sessions"]:,} sessions'
    # Lead "By the numbers" stat adapts so a non-delegating user (most Codex/Gemini users, and
    # plenty of Claude ones) never gets a weak "0.0 agents / session" headline: agents/session
    # for real delegators → else reasoning blocks → else lines edited (all universally non-zero).
    if b["delegate_actions"] >= 20 and per_sess >= 0.5:
        _first_stat = [f'{per_sess}', "agents / session"]
    elif v["thinking_blocks"] >= 50:
        _first_stat = [f'{v["thinking_blocks"]:,}', "reasoning blocks"]
    else:
        _first_stat = [f'{vel["tool_churn_edit_write"]:,}', "lines edited"]
    card_data = _js({
        "arch": archetype,
        "tagline": _tag,
        "context": _context,
        "scores": [[k, val, SCORE_NOTES_SHORT.get(k, "")] for k, val in scores.items()],
        "steering": {"label": steer_read["label"], "gloss": steer_read["gloss"]},  # poster uses the short gloss; the longer detail is page-only
        "stats": [_first_stat,
                  [f'{v["total_prompts"]:,}', "prompts"],
                  [f'{v["tool_calls_total"]:,}', "tool calls"],
                  [f'{vel["git_churn_total"]:,}', "git lines"]],
        "cards": poster_cards,
        "logo": logo,
    })

    caption = ("My “how I build with AI” profile, computed 100% locally — nothing uploaded. "
               "Made with paxel-local, an MIT rebuild of YC's Paxel that keeps your sessions on your machine. "
               "Run your own: " + REPO_URL)

    eyebrow = (f'{v["total_sessions"]} sessions · {v["total_prompts"]:,} prompts · '
               f'{v["tool_calls_total"]:,} tool calls · {_d10(c["date_range"][0])} → {_d10(c["date_range"][1])}')

    parts = []
    P = parts.append
    P("<!DOCTYPE html>")
    P("<!-- Generated locally by paxel.py. Zero data left this machine. Counts measured; archetype/scores are a rubric. -->")
    P('<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">')
    P("<title>Builder Profile — Roadmap</title>")
    if logo:
        P(f'<link rel="icon" href="{logo}">')
    P(_PROFILE_CSS)
    P('</head><body><div id="report">')
    P('<div class="topbar"><div class="wrap">'
      f'<a class="brandlink" href="https://www.roadmap.chat/community" target="_blank" rel="noopener" title="Roadmap — find your flock">'
      f'{chip}<span class="brand">Roadmap <span class="dim">· Builder Profile</span></span></a>'
      '<span class="badge">🔒 Generated locally · nothing uploaded</span></div></div>')
    P('<div class="wrap"><section class="hero">')
    P(f'<p class="eyebrow">{eyebrow}</p>')
    P(f'<h1>{_hero_lead(archetype)}<br><span class="accent">{_h.escape(archetype)}.</span></h1>')
    P(f'<p class="quote">“{_h.escape(quote)}”</p>')
    P(f'<p class="sub"><b>{v["thinking_blocks"]:,} reasoning blocks</b> before the diffs, '
      f'<b>{b["delegate_actions"]:,} subagents</b> dispatched, and <b>{b["tool_errors"]:,} errors</b> recovered from along the way.</p>')
    P('<div class="stat-strip">'
      f'<div><span class="n mono">{vel["git_churn_total"]:,}</span><span class="l">lines committed to git</span></div>'
      f'<div><span class="n mono">{vel["tool_churn_edit_write"]:,}</span><span class="l">lines via Edit/Write</span></div>'
      f'<div><span class="n mono">~{vel["shell_authored_lines_est"]:,}</span><span class="l">lines in the shell</span></div>'
      f'<div><span class="n mono">{b["iteration_depth_max"]}</span><span class="l">max edits, one file</span></div>'
      f'<div><span class="n mono">{b["delegate_actions"]:,}</span><span class="l">agents you ran</span></div></div>')
    P('<div class="share"><span class="lbl">Share:</span>'
      '<a id="share-x" class="btn x" href="#" target="_blank" rel="noopener">'
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231 5.45-6.231Zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77Z"/></svg>Post on X</a>'
      '<button id="share-copy" class="btn ghost" type="button">📋 Copy caption</button>'
      '<button id="share-img" class="btn ghost" type="button">🖼 Download image</button></div>')
    P('</section><h2 class="section">Your scorecard</h2>')
    P('<div class="disclaimer"><b>Counts are measured; the three scores are a read on your style</b>, '
      'grounded in <a href="https://github.com/garrytan/gstack" target="_blank" rel="noopener">gstack</a> '
      '— how you work, not a ranking of how good you are. <b>Steering isn\'t scored</b>: how hands-on you '
      'run agents has no better or worse end, so it\'s described, not graded.</div>')
    if _evidence(stats) < 0.5:   # < ~1000 tool calls: too thin to read habits confidently
        P(f'<div class="disclaimer" style="border-left-color:var(--muted)">⚠ <b>Limited data.</b> '
          f'Just {v["total_sessions"]} sessions and {v["tool_calls_total"]:,} tool calls here — not enough to read '
          f'your habits with confidence, so these scores lean toward the middle. Run more and check back.</div>')
    P(score_rows)
    P(f'<div class="steerread"><span class="sr-k">Steering</span>'
      f'<span class="sr-v"><b>{_h.escape(steer_read["label"])}</b> — {_h.escape(steer_read["gloss"])}</span>'
      f'<span class="sr-d">{_h.escape(steer_read["detail"])}</span></div>')
    if moves:
        P('<h2 class="section">Your signature moves</h2>')
        P('<p class="lead">The patterns in how you direct the AI, pulled from your real sessions. The tag on each '
          'card is the gstack stage it maps to.</p>')
        P(f'<div class="grid">{moves_html}</div>')
    if edges:
        P('<h2 class="section">Your growth edge</h2>')
        P('<p class="lead">A few habits to try — each pulled from your own data, not a generic checklist. The '
          '<code>/commands</code> in parentheses are optional tools from '
          '<a href="https://github.com/garrytan/gstack" target="_blank" rel="noopener">gstack</a> '
          'if you\'d rather automate one of them.</p>')
        P(f'<div class="grid">{edges_html}</div>')
    P('<h2 class="section">What we noticed</h2><div class="grid">')
    P("".join(cards))
    P('</div>')

    # "In your own words" — VERBATIM prompt quotes (each already _safe_quote-filtered for
    # secrets/PII upstream). Rendered on the local page (gitignored). The go-to and the
    # off-the-cuff also feed the shareable poster (see poster_cards above) — the off-cuff via
    # a LIVE read of #q-cuff at download, so a reroll is honored. The crash-out stays
    # page-only. Escape every quote (raw user text → XSS). Only render cards that exist.
    voice = voice or {}
    vcards = []
    quote_js = {}   # target -> [raw quotes] for the ↻ reroll button (cycles the pool client-side)

    def _quote_card(eyebrow, target, pool, desc):
        quote_js[target] = pool
        reroll = (f' <button type="button" class="reroll" data-target="{target}">&#8635; another</button>'
                  if len(pool) > 1 else "")
        return (f'<div class="card"><p class="q">{eyebrow}{reroll}</p>'
                f'<p class="a" id="q-{target}">&ldquo;{_h.escape(pool[0])}&rdquo;</p>'
                f'<p class="d">{desc}</p></div>')

    if voice.get("goto"):
        ph, cnt, ns = voice["goto"]
        vcards.append(_card("What's your go-to prompt?", f'&ldquo;{_h.escape(ph)}&rdquo;',
              f'Your most-repeated prompt — <b>{cnt:,}</b> times across {ns} sessions.'))
    if voice.get("crashouts"):
        vcards.append(_quote_card("Your biggest crash-out?", "crashout", voice["crashouts"],
              "One of your most heated prompts. We&rsquo;ve all been there."))
    if voice.get("cryptics"):
        vcards.append(_quote_card("Off the cuff?", "cuff", voice["cryptics"],
              "One of your more unfiltered asks — straight from the keyboard, unedited."))
    if vcards:
        P('<h2 class="section">In your own words</h2>')
        P('<p class="lead">Pulled <b>verbatim</b> from your real prompts (filtered for secrets &amp; PII) — '
          'hit <b>&#8635; another</b> to reroll. Your go-to and off-the-cuff lines also land on the shareable '
          'image; the off-the-cuff one uses <b>whichever you&rsquo;ve rerolled to</b>, so land on one you like '
          'before you download. Everything else stays on this local page, on your machine.</p>')
        P(f'<div class="grid">{"".join(vcards)}</div>')

    P('<footer><span class="lock">🔒 Generated entirely on-device</span> by <span class="mono">paxel.py</span> — '
      'the same analysis Paxel runs, with zero data sent anywhere. Counts measured from your transcripts; '
      'archetype &amp; scores are a rubric. Raw metrics in <span class="mono">stats.json</span>.<br>'
      'Built by <a class="by" href="https://github.com/Photobombastic" target="_blank" rel="noopener">Max Schilling</a>, '
      '<a href="https://www.roadmap.chat/community" target="_blank" rel="noopener">Roadmap</a></footer>')
    P('</div></div>')
    P("<script>(function(){")
    P('var QUOTES=' + _js(quote_js) + ';var QIDX={};')
    P('document.querySelectorAll(".reroll").forEach(function(b){b.addEventListener("click",function(){'
      'var t=b.getAttribute("data-target"),arr=QUOTES[t];if(!arr||arr.length<2)return;'
      'QIDX[t]=((QIDX[t]||0)+1)%arr.length;var el=document.getElementById("q-"+t);'
      'if(el)el.textContent="\\u201c"+arr[QIDX[t]]+"\\u201d";});});')
    P(f'var caption={_js(caption)};')
    P('var x=document.getElementById("share-x");if(x)x.href="https://x.com/intent/tweet?text="+encodeURIComponent(caption);')
    P('var cb=document.getElementById("share-copy");if(cb)cb.addEventListener("click",function(){'
      'var d=function(){var o=cb.textContent;cb.textContent="✓ Copied";setTimeout(function(){cb.textContent=o;},1500);};'
      'if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(caption).then(d).catch(fb);}else{fb();}'
      'function fb(){var ta=document.createElement("textarea");ta.value=caption;document.body.appendChild(ta);ta.select();'
      'try{document.execCommand("copy");}catch(e){}document.body.removeChild(ta);d();}});')
    P('var CARD=' + card_data + ';')
    P(r'''var ib=document.getElementById("share-img");
if(ib)ib.addEventListener("click",function(){
  try{
    if(typeof HTMLCanvasElement==="undefined"||!HTMLCanvasElement.prototype.toBlob){alert("Image export isn't supported in this browser — try a screenshot.");return;}
    var W=1200,M=48,s=3,IW=W-2*M;   // 3x supersample so the logo art stays crisp when zoomed/retina
    var beak="#ED7379",beakD="#D14E57",slate="#313941",mut="#5e6a73",line="#dfe3e7",track="#dde2e6";
    function L(c,t,mw){var ws=String(t).split(" "),ln="",o=[];for(var i=0;i<ws.length;i++){var tn=ln?ln+" "+ws[i]:ws[i];if(c.measureText(tn).width>mw&&ln){o.push(ln);ln=ws[i];}else ln=tn;}o.push(ln);return o;}
    function rr(c,x,y,w,h,r){c.beginPath();c.moveTo(x+r,y);c.arcTo(x+w,y,x+w,y+h,r);c.arcTo(x+w,y+h,x,y+h,r);c.arcTo(x,y+h,x,y,r);c.arcTo(x,y,x+w,y,r);c.closePath();}
    function box(c,x,y,w,h){c.save();c.shadowColor="rgba(40,50,60,.10)";c.shadowBlur=20;c.shadowOffsetY=7;c.fillStyle="#fff";rr(c,x,y,w,h,16);c.fill();c.restore();c.strokeStyle="#e8ebee";c.lineWidth=1;rr(c,x,y,w,h,16);c.stroke();}
    function mini(c,x,y,w,h,card){
      var pad=20,iw=w-2*pad,cx=x+w/2;box(c,x,y,w,h);c.textAlign="center";
      c.fillStyle=beakD;c.font="700 10.5px -apple-system,sans-serif";if(c.letterSpacing!==undefined)c.letterSpacing="1px";
      var el=L(c,String(card.eyebrow).toUpperCase(),iw);if(el.length>2)el=el.slice(0,2);
      for(var k=0;k<el.length;k++)c.fillText(el[k],cx,y+pad+11+k*14);if(c.letterSpacing!==undefined)c.letterSpacing="0px";
      // TOP-ANCHOR the content (not vertically centered) so every headline in a row shares
      // a baseline; leftover whitespace collects at the bottom of shorter cards.
      var ebBot=y+pad+11+(el.length-1)*14+6,gTop=ebBot+14,q=card.mode==="quote";
      var hfs=q?29:23;function hf(z){return (q?"italic 800 ":"800 ")+z+"px Georgia,serif";}
      var head=q?("“"+card.headline+"”"):card.headline;c.font=hf(hfs);var hl=L(c,head,iw);
      while(hl.length>2&&hfs>16){hfs-=1;c.font=hf(hfs);hl=L(c,head,iw);}
      if(hl.length>2){hl=hl.slice(0,2);hl[1]=hl[1].replace(/[\s—-]+$/,"")+"…";}
      var hLH=hfs+4;c.fillStyle="#181c1f";c.font=hf(hfs);for(var k=0;k<hl.length;k++)c.fillText(hl[k],cx,gTop+hfs-2+k*hLH);
      c.font="400 13px -apple-system,sans-serif";var sl=L(c,card.sub,iw),smax=q?2:3;
      if(sl.length>smax){sl=sl.slice(0,smax);sl[smax-1]=sl[smax-1].replace(/[\s—-]+$/,"")+"…";}
      var sTop=gTop+hl.length*hLH+12;c.fillStyle=mut;c.font="400 13px -apple-system,sans-serif";
      for(var k=0;k<sl.length;k++)c.fillText(sl[k],cx,sTop+11+k*18);
      c.textAlign="left";
    }
    // WYSIWYG: pull whatever quote is showing on the page now into any "live" card (off-cuff reroll)
    var cards=CARD.cards.map(function(cd){
      if(cd.live){var el=document.getElementById("q-"+cd.live);
        if(el){var t=el.textContent.replace(/^[\s“"]+/,"").replace(/[\s”"]+$/,"");if(t)cd=Object.assign({},cd,{headline:t});}}
      return cd;});
    // layout — tightened top gap; height grows with the card count
    var mc=document.createElement("canvas").getContext("2d");
    var afs=88;mc.font="800 "+afs+"px Georgia,serif";while(mc.measureText(CARD.arch+".").width>IW&&afs>48){afs-=2;mc.font="800 "+afs+"px Georgia,serif";}
    mc.font="italic 27px Georgia,serif";var tll=L(mc,CARD.tagline,IW);if(tll.length>2){tll=tll.slice(0,2);tll[1]=tll[1].replace(/[\s—-]+$/,"")+"…";}   // tagline can wrap to 2 lines
    var heroY=96,archB=heroY+12+Math.round(afs*0.74),tagY=archB+40,tagLH=33,ctxY=tagY+(tll.length-1)*tagLH+30,scY=ctxY+42,scH=348,scEnd=scY+scH;
    var gridY=scEnd+30,gc=4,rows=Math.ceil(cards.length/gc),cardH=184,gapY=22;
    var gridEnd=rows>0?gridY+rows*cardH+(rows-1)*gapY:scEnd,footerY=gridEnd+44,H=footerY+34;
    while(s>1&&(W*s*H*s>16700000||H*s>4096))s--;   // iOS canvas-area/max-dim guard: degrade to a lower-res image rather than a silently-blank one
    var cv=document.createElement("canvas");cv.width=W*s;cv.height=H*s;
    var c=cv.getContext("2d");c.scale(s,s);c.textBaseline="alphabetic";c.textAlign="left";
    c.imageSmoothingEnabled=true;c.imageSmoothingQuality="high";   // proper resample of the logo, not a cheap box filter
    function finish(){cv.toBlob(function(bl){if(!bl){alert("Image export failed — try a screenshot.");return;}var u=URL.createObjectURL(bl);var a=document.createElement("a");a.href=u;a.download="builder-profile.png";a.click();setTimeout(function(){URL.revokeObjectURL(u);},4000);});}
    c.fillStyle="#edeff2";c.fillRect(0,0,W,H);c.fillStyle=beak;c.fillRect(0,0,W,8);
    var bx0=CARD.logo?M+76:M;
    c.fillStyle=slate;c.font="700 26px -apple-system,sans-serif";c.fillText("Roadmap",bx0,64);
    c.font="600 13px -apple-system,sans-serif";var bt="Generated locally · nothing uploaded",btw=c.measureText(bt).width,btx=W-M-btw;
    c.save();c.strokeStyle=mut;c.fillStyle=mut;c.lineWidth=1.5;c.beginPath();c.arc(btx-12,55,3,Math.PI,2*Math.PI);c.stroke();rr(c,btx-17,55,10,8,2);c.fill();c.restore();
    c.fillStyle=mut;c.fillText(bt,btx,61);
    c.fillStyle=beakD;c.font="700 13px -apple-system,sans-serif";if(c.letterSpacing!==undefined)c.letterSpacing="2px";c.fillText("YOUR BUILDER PROFILE",M,heroY);if(c.letterSpacing!==undefined)c.letterSpacing="0px";
    c.font="800 "+afs+"px Georgia,serif";c.fillStyle=beak;c.fillText(CARD.arch+".",M,archB);
    c.fillStyle="#3b444b";c.font="italic 27px Georgia,serif";for(var ti=0;ti<tll.length;ti++)c.fillText(tll[ti],M,tagY+ti*tagLH);
    if(CARD.context){c.fillStyle=mut;c.font="500 15px -apple-system,sans-serif";c.fillText(CARD.context,M,ctxY);}
    box(c,M,scY,IW,scH);
    var pad=40,ix=M+pad,half=IW/2;
    c.fillStyle=mut;c.font="700 13px -apple-system,sans-serif";if(c.letterSpacing!==undefined)c.letterSpacing="1px";c.fillText("GSTACK SCORECARD",ix,scY+50);
    var stx=M+half+38;c.fillText("BY THE NUMBERS",stx,scY+50);if(c.letterSpacing!==undefined)c.letterSpacing="0px";
    var sc=CARD.scores,base=scY+96,rh=64,barL=ix+150,barR=M+half-86,valX=barR+46;
    for(var i=0;i<sc.length;i++){var ry=base+i*rh,nm=sc[i][0],vl=sc[i][1],note=sc[i][2]||"";
      c.fillStyle=slate;c.font="700 16px -apple-system,sans-serif";c.fillText(nm,ix,ry);
      var bw2=barR-barL,bh=13,by=ry-13;c.fillStyle=track;rr(c,barL,by,bw2,bh,6);c.fill();
      var g=c.createLinearGradient(barL,0,barL+bw2,0);g.addColorStop(0,beakD);g.addColorStop(1,beak);c.fillStyle=g;rr(c,barL,by,Math.max(bh,bw2*(vl/10)),bh,6);c.fill();
      c.fillStyle="#16191d";c.font="800 17px ui-monospace,Menlo,monospace";c.textAlign="right";c.fillText(Number(vl).toFixed(1),valX,ry);c.textAlign="left";
      c.fillStyle=mut;c.font="400 13px -apple-system,sans-serif";c.fillText(note,ix,ry+22);}
    if(CARD.steering){var sry=base+sc.length*rh;                       // Steering: described, not graded — no bar, no number
      c.fillStyle=slate;c.font="700 16px -apple-system,sans-serif";c.fillText("Steering",ix,sry);
      c.fillStyle=beakD;c.font="700 15px -apple-system,sans-serif";c.fillText(CARD.steering.label,barL,sry);
      c.fillStyle=mut;c.font="400 13px -apple-system,sans-serif";c.fillText(CARD.steering.gloss,ix,sry+22);}
    var dvx=M+half+4;c.strokeStyle=line;c.lineWidth=1;c.beginPath();c.moveTo(dvx,scY+38);c.lineTo(dvx,scY+scH-34);c.stroke();
    var stt=CARD.stats||[];for(var j=0;j<stt.length&&j<sc.length+1;j++){var syy=base+j*rh;
      c.fillStyle=slate;c.font="800 30px ui-monospace,Menlo,monospace";c.fillText(stt[j][0],stx,syy);var w2=c.measureText(stt[j][0]).width;
      c.fillStyle=mut;c.font="500 14px -apple-system,sans-serif";c.fillText(stt[j][1],stx+w2+12,syy);}
    var gapX=16,colW=(IW-(gc-1)*gapX)/gc;
    for(var i=0;i<cards.length;i++){var row=Math.floor(i/gc),col=i%gc;
      var inRow=Math.min(gc,cards.length-row*gc);            // cards in THIS row (last row may be partial)
      var x0=M+(IW-(inRow*colW+(inRow-1)*gapX))/2;           // center the row → partial rows don't jam left
      mini(c,x0+col*(colW+gapX),gridY+row*(cardH+gapY),colW,cardH,cards[i]);}
    c.fillStyle=mut;c.font="500 14px -apple-system,sans-serif";c.textAlign="center";c.fillText("Generated 100% on-device — nothing uploaded · github.com/Photobombastic/paxel-local",W/2,footerY);c.textAlign="left";
    if(CARD.logo){var im=new Image();im.onload=function(){
      var k=Math.min(54/im.width,54/im.height),lw=im.width*k,lh=im.height*k;   // contain-fit: never squish the logo's aspect
      c.drawImage(im,M+(54-lw)/2,32+(54-lh)/2,lw,lh);finish();};im.onerror=finish;im.src=CARD.logo;}else{finish();}
  }catch(e){alert("Image export failed — try a screenshot.");}
});''')
    P("})();</script></body></html>")
    with open(os.path.join(OUT_DIR, "profile.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
