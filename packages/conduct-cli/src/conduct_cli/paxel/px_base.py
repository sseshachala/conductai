"""paxel base: split out of the original single-file paxel.py."""

import os
import re
import subprocess
import sys
from datetime import datetime

BASE = os.path.expanduser("~/.claude/projects")
# Outputs go next to the paxel/ directory (the scratch dir it was copied into).
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- tool taxonomy -----------------------------------------------------------
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Grep", "Glob", "NotebookRead"}
DISCOVER_TOOLS = {"WebSearch", "WebFetch", "ToolSearch"}
EXEC_TOOLS = {"Bash", "BashOutput", "KillShell"}
DELEGATE_TOOLS = {"Agent", "Task"}
PLAN_TOOLS = {"TodoWrite", "TodoRead", "ExitPlanMode", "EnterPlanMode", "EnterWorktree",
              "ExitWorktree", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}
SCHEDULE_TOOLS = {"ScheduleWakeup", "CronCreate", "CronDelete", "CronList",
                  "RemoteTrigger", "PushNotification", "Monitor"}
SKILL_TOOLS = {"Skill"}
ASK_TOOLS = {"AskUserQuestion"}

# verbs that mark an MCP tool as read/inspect rather than produce/act
MCP_INSPECT_HINTS = ("read", "get", "list", "search", "find", "describe",
                     "snapshot", "screenshot", "query", "fetch", "whoami",
                     "details", "status", "info", "show", "doc_")


def classify_tool(name: str) -> str:
    if name in WRITE_TOOLS:
        return "produce"
    if name in READ_TOOLS or name in DISCOVER_TOOLS or name in PLAN_TOOLS:
        return "explore"
    if name in EXEC_TOOLS:
        return "execute"
    if name in DELEGATE_TOOLS:
        return "delegate"
    if name in SKILL_TOOLS:
        return "execute"
    if name in SCHEDULE_TOOLS:
        return "execute"
    if name in ASK_TOOLS:
        return "ask"
    if name.startswith("mcp__"):
        last = name.split("__")[-1].lower()
        if any(h in last for h in MCP_INSPECT_HINTS):
            return "explore"
        return "produce"
    return "other"


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except Exception:
        return None


def line_count(s):
    if not s:
        return 0
    return s.count("\n") + (1 if s and not s.endswith("\n") else 0)


def strip_injections(text):
    """Remove injected wrappers so prompt length reflects what the human typed."""
    import re
    if not text:
        return ""
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    text = re.sub(r"<command-name>.*?</command-name>", "", text, flags=re.S)
    text = re.sub(r"<command-message>.*?</command-message>", "", text, flags=re.S)
    text = re.sub(r"<command-args>.*?</command-args>", "", text, flags=re.S)
    text = re.sub(r"<local-command-stdout>.*?</local-command-stdout>", "", text, flags=re.S)
    return text.strip()


# a Bash command writes/modifies a file if it redirects (not to /dev/null),
# uses a heredoc, sed -i, or tee — used to estimate shell-authored churn the
# Edit/Write tools never see.
_REDIR = re.compile(r'(?<!2)>{1,2}(?!\s*(?:/dev/null|&\d))')


def bash_writes_file(cmd):
    return bool(_REDIR.search(cmd)
                or re.search(r'<<(?!<)', cmd)            # heredoc, not a <<< here-string
                or re.search(r'\bsed\s+-i', cmd)
                or re.search(r'\btee\s+(?![>|])', cmd))   # tee to a file, not a process sub


# A Bash command that RUNS A TEST SUITE — so a builder who does TDD through the shell
# (pytest / go test / npm test …) isn't read as "0 test runs" just because they don't use a
# named gstack test-skill. Critical fix: skill-name-only detection was blind to CLI testing,
# the single most common way people actually test. Matches the runner invocation, not the
# bare word "test" (so it won't fire on "latest" or "git request").
_SHELL_TEST_RE = re.compile(
    r'(?:^|[\s;&|(/])('          # start / separator / '/' → so ./venv/bin/pytest, node_modules/.bin/jest match
    r'pytest|py\.test|tox|nox|nosetests?|unittest|coverage\s+run|hypothesis'
    r'|jest|vitest|mocha|jasmine|ava|cypress|playwright\s+test|wtr|web-test-runner|karma'
    r'|go\s+test|gotestsum|cargo\s+test|cargo\s+nextest'
    r'|rspec|minitest|rails\s+test|phpunit|pest'
    r'|ctest|gtest|catch2'
    r'|\./gradlew\s+(?:test|check)|gradle\s+(?:test|check)|mvn\s+(?:test|verify)'
    r'|dotnet\s+test|xunit|nunit'
    r'|(?:npm|yarn|pnpm|bun)\s+(?:run\s+)?test'
    r'|rake\s+(?:test|spec)|make\s+(?:test|check)'
    r'|bazel\s+test|elixir\s+test|mix\s+test|swift\s+test|flutter\s+test|deno\s+test'
    r'|hatch\s+run\s+test'
    r')(?=$|[\s;&|):])', re.I)   # trailing guard kills ava.json / nox/ / tox.ini / *cache; ':' keeps npm test:unit


def bash_runs_tests(cmd):
    return bool(_SHELL_TEST_RE.search(cmd or ""))


def _git(cwd, args, timeout=30):
    """Run a git command locally; return stdout or '' on any failure. Never raises."""
    try:
        p = subprocess.run(["git", "-C", cwd] + args, capture_output=True,
                           text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""


def git_churn(cwds, since_iso, until_iso):
    """Gold-standard churn: real insertions/deletions from `git log --numstat`,
    capturing EVERY committed change regardless of how it was made (Edit, Bash,
    vim, etc.). 100% local — git reads .git on disk, nothing is uploaded.
    Repos that are missing/non-git are reported as unavailable, not silently dropped.
    """
    # Dedupe by repo IDENTITY (root-commit SHA), not path — otherwise multiple
    # clones/worktrees of the same project (e.g. a fork + a worktree + a copy)
    # each contribute the same commits and inflate the total.
    tops = {}                       # identity -> toplevel path (first seen)
    for cwd in cwds:
        if not cwd or not os.path.isdir(cwd):
            continue
        top = _git(cwd, ["rev-parse", "--show-toplevel"]).strip()
        if not top:
            continue
        root = _git(top, ["rev-list", "--max-parents=0", "HEAD"]).split()
        if root:
            ident = "root:" + ",".join(sorted(root))
        else:
            remote = _git(top, ["config", "remote.origin.url"]).strip()
            ident = "remote:" + remote if remote else "path:" + top
        tops.setdefault(ident, top)
    per_repo, ins_tot, del_tot, commits_tot = [], 0, 0, 0
    for top in sorted(tops.values()):
        email = _git(top, ["config", "user.email"]).strip()
        args = ["log", "--numstat", "--no-merges",
                f"--since={since_iso}", f"--until={until_iso}",
                "--pretty=tformat:__C__"]
        if email:
            args.append(f"--author={email}")
        out = _git(top, args)
        ins = dels = commits = 0
        for ln in out.splitlines():
            if ln == "__C__":
                commits += 1
                continue
            parts = ln.split("\t")
            if len(parts) == 3:
                a, d, _ = parts
                if a.isdigit():
                    ins += int(a)
                if d.isdigit():
                    dels += int(d)
        if ins or dels or commits:
            per_repo.append((os.path.basename(top), ins, dels, commits))
            ins_tot += ins
            del_tot += dels
            commits_tot += commits
    per_repo.sort(key=lambda x: -(x[1] + x[2]))
    return {
        "repos_seen": len(tops),
        "repos_with_commits": len(per_repo),
        "insertions": ins_tot,
        "deletions": del_tot,
        "churn": ins_tot + del_tot,
        "commits": commits_tot,
        "per_repo": per_repo[:12],
    }


def pctile(sorted_vals, p):
    if not sorted_vals:
        return 0
    k = max(0, min(len(sorted_vals) - 1, int(round((p / 100) * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


# ---------------------------------------------------------------------------
# Multi-source discovery + translators. Each non-Claude format is translated
# into Claude-shaped event dicts so the single aggregation loop in main() works
# unchanged across tools. Every read is local — nothing is uploaded.
# Solid/tested: Claude Code, Codex CLI, Gemini CLI, Pi, opencode, Cursor.
# ---------------------------------------------------------------------------
CODEX_DIR = os.path.expanduser("~/.codex/sessions")
GEMINI_DIR = os.path.expanduser("~/.gemini/tmp")
PI_DIR = os.path.expanduser("~/.pi/agent/sessions")
OPENCODE_DIR = os.path.expanduser("~/.local/share/opencode")
CURSOR_DIR = os.path.expanduser("~/.cursor/projects")


def _cursor_db_path():
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Cursor/User/globalStorage/state.vscdb")
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return os.path.join(appdata, "Cursor", "User", "globalStorage", "state.vscdb")
    return os.path.expanduser("~/.config/Cursor/User/globalStorage/state.vscdb")


CURSOR_DB = _cursor_db_path()
ALL_SOURCES = ("claude", "codex", "gemini", "pi", "opencode", "cursor")


def _texts(content):
    """Join text from a Claude/Codex/Gemini/Pi/opencode content list (or plain string)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict):
                out.append(b.get("text") or b.get("input_text") or b.get("output_text") or "")
            elif isinstance(b, str):
                out.append(b)
        return "\n".join(x for x in out if x)
    return ""


def _iso_ms(ms):
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000).astimezone().isoformat()
    except Exception:
        return None


def _canon_tool(name):
    """Normalize Pi/opencode lower-case tool names to the Claude-style taxonomy."""
    n = str(name or "tool")
    key = n.lower().replace("-", "_")
    mapping = {
        "bash": "Bash", "shell": "Bash", "exec": "Bash", "run": "Bash",
        "read": "Read", "grep": "Grep", "glob": "Glob", "list": "Glob", "ls": "Glob",
        "edit": "Edit", "patch": "Edit", "write": "Write", "multi_edit": "MultiEdit",
        "todowrite": "TodoWrite", "todo_write": "TodoWrite", "todoread": "TodoRead",
        "task": "Agent", "agent": "Agent", "webfetch": "WebFetch", "web_fetch": "WebFetch",
        "websearch": "WebSearch", "web_search": "WebSearch",
    }
    return mapping.get(key, n)


def _canon_input(name, inp):
    """Normalize common argument names enough for churn/test metrics to work."""
    if not isinstance(inp, dict):
        return {}
    out = dict(inp)
    cname = _canon_tool(name)
    if cname == "Bash":
        out.setdefault("command", out.get("cmd") or out.get("command") or out.get("script") or "")
    elif cname in ("Read", "Write", "Edit", "MultiEdit"):
        if "filePath" in out and "file_path" not in out:
            out["file_path"] = out["filePath"]
        if "path" in out and "file_path" not in out:
            out["file_path"] = out["path"]
    if cname == "Write" and "content" not in out:
        out["content"] = out.get("text") or ""
    if cname == "Edit":
        out.setdefault("old_string", out.get("oldString") or out.get("old") or "")
        out.setdefault("new_string", out.get("newString") or out.get("new") or out.get("content") or "")
    return out


# Politeness markers in your own prompts (for the "how polite are you" card). Word-boundaried.
_POLITE_RE = re.compile(r'\b(thanks|thank you|thank u|thx|please|pls|appreciate|'
                        r'much appreciated|good (?:job|work)|nice work|well done)\b', re.I)

# --- "In your own words" cards: pulled VERBATIM from your real prompts. These quote raw
# session text, so they render ONLY on the local page and are deliberately kept OUT of the
# shareable download card (see card_data). HTML-escape every quote before injecting it. ---
_TYPO_WORDS = {"teh", "hte", "thge", "wrok", "adn", "nad", "recieve", "seperate", "definately",
               "thier", "alot", "wtih", "wiht", "taht", "thta", "jsut", "becuase", "plz", "pls",
               "u", "ur", "r", "y", "k", "yea", "yeah", "yep", "yup", "nope", "lol", "lmao", "idk",
               "dont", "wont", "cant", "doesnt", "didnt", "couldnt", "wouldnt", "isnt", "wasnt",
               "youre", "theyre", "thats", "whats", "hows", "im", "ive", "ill", "id", "hes", "shes",
               "wodn", "fo", "ot", "si", "hmm", "hmmm", "wat", "wut", "tho", "thru", "fix", "undo",
               "nvm", "rn", "btw", "fr", "ok", "okay", "kk", "gah", "ugh", "argh", "oof",
               "wtf", "wth", "omg", "ya", "nah", "meh", "huh", "welp", "oop", "oops", "aight"}


def _typo_score(text):
    """Rough 'how garbled/casual is this' score — counts likely-typo / texting tokens.
    Heuristic, not a spell-checker; only used to surface a genuinely odd REAL prompt."""
    s = 0
    for t in re.findall(r"[a-z0-9']+", text.lower()):
        if t in _TYPO_WORDS:
            s += 1
        elif len(t) >= 4 and not re.search(r'[aeiou]', t):   # a vowel-less chunk
            s += 1
        elif re.search(r'(.)\1\1', t):                        # 3+ of the same letter (loool, yesss)
            s += 1
        elif re.search(r'[a-z]\d|\d[a-z]', t):                # digits glued into a word
            s += 1
        elif "'" not in t and t.endswith(("nt", "re", "ll", "ve")) and t in _TYPO_WORDS:
            s += 1                                            # missing apostrophe (dont, youre)
    return s


def _caps_ratio(text):
    letters = [c for c in text if c.isalpha()]
    return (sum(1 for c in letters if c.isupper()) / len(letters)) if letters else 0.0


# Frustration / distress markers for the "biggest crash-out" card — these gate it, so a
# clean all-caps EXCITEMENT prompt ("ONWARDS", "PUSH THRU") doesn't read as a meltdown.
_RAGE_RE = re.compile(r'\b(wtf|wth|ffs|ugh+|argh+|seriously|literally|stop+|nope|why+|'
                      r'are you (?:kidding|serious|sure|joking)|come on|for real|already said|'
                      r'i said|told you|do ?not|dont|cant|never|jesus|christ|damn|hell|crap|'
                      r'shit|fuck\w*|wrong|broke|broken|nightmare|stuck|fail\w*|hate|pressure|'
                      r'stress\w*|overwhelm\w*|dying|exhaust\w*|help|no+\b|not\b)\b', re.I)


def _crashout_score(text, hour=None):
    """How 'heated' a prompt reads — caps, exclamation pile-ups, ALLCAPS words, frustration
    words, and BREVITY (terse all-caps menace — 'NO STOP', 'SOMETHING IS WRONG' — is funnier
    than a long rant). A 2–6am prompt gets extra weight too: the witching-hour grind is its
    own genre of crash-out. Pulls a REAL prompt, never invents one."""
    wc = len(text.split())
    caps = _caps_ratio(text)
    bangs = min(text.count("!") + text.count("?"), 5)
    allcaps = min(len(re.findall(r'\b[A-Z]{3,}\b', text)), 4)
    rage = min(len(_RAGE_RE.findall(text)), 3)
    brevity = max(0, 9 - wc) * 0.5
    witching = 1.8 if hour is not None and 2 <= hour < 6 else 0   # 2–6am: posted from the trenches
    return caps * 2.5 + brevity + allcaps * 0.4 + rage * 0.5 + bangs * 0.3 + witching


_FEELS_RE = re.compile(r'\b(worried|scared|nervous|anxious|stressed|exhausted|confused|'
                       r'stupid|dumb|idiot|hopeless|unemploy\w*|crying|sobbing|sad|miserable|'
                       r'overwhelmed|panic\w*|dying|losing my mind|cant anymore|please work)\b', re.I)
_EMOTICON_RE = re.compile(r"[:;=]['\-^]?[\(\)\[\]\/\\|dpox3<>]", re.I)
# Content-free affirmations/fillers — an "off the cuff" card needs more than "yep :)".
_FILLER = {"ok", "okay", "yes", "yep", "yup", "yeah", "ya", "sure", "nice", "great", "cool",
           "perfect", "thanks", "thank", "you", "done", "k", "kk", "good", "awesome", "love",
           "got", "it", "this", "that", "lol", "haha", "nvm", "fine", "right", "correct", "exactly"}


def _cryptic_score(text):
    """The funniest off-the-cuff prompts: tiny, typo'd, lowercase, vague, and — the gold —
    a stray emoticon or a flash of human vulnerability ('Im worried im unemploybale :(')."""
    wc = len(text.split())
    typ = _typo_score(text)
    vague = len(re.findall(r'\b(it|that|this|the thing|those|them|stuff|one)\b', text, re.I))
    lower = 1 if text == text.lower() else 0
    nopunct = 1 if not re.search(r'[.?!]', text.strip()) else 0
    short = max(0, 7 - wc) * 0.25
    emo = 1.6 if _EMOTICON_RE.search(text) else 0
    feels = 1.3 if _FEELS_RE.search(text) else 0
    return typ * 1.0 + vague * 0.55 + lower * 0.5 + nopunct * 0.35 + short + emo + feels


# A prompt can be surfaced verbatim only if it's actually the user's words — not a harness
# marker, and not carrying a secret. We NEVER alter a shown prompt (Max: zero redaction); we
# just refuse to SELECT one that's a credential or a system artifact rather than a real prompt.
_SECRET_RE = re.compile(r'eyJ[A-Za-z0-9_\-]{20,}|sk-[A-Za-z0-9]{16,}|gh[posru]_[A-Za-z0-9]{16,}|'
                        r'AKIA[0-9A-Z]{12,}|Bearer\s+\S{16,}|[A-Fa-f0-9]{32,}|[A-Za-z0-9_\-]{36,}', re.I)
_SYS_MARKER_RE = re.compile(r'\[request interrupted|\[image\b|\[image\s*#|\[pasted|\[tool|'
                            r'<system|<command|<local-command|this block is not|tool_use|caveat:', re.I)


def _safe_quote(text):
    if not text or len(text) > 140:
        return False
    if _SYS_MARKER_RE.search(text) or _SECRET_RE.search(text):
        return False
    if any(len(tok) > 32 for tok in text.split()):   # a giant unbroken token = key/url/hash, not a word
        return False
    toks = text.split()
    if len(toks) == 1 and re.fullmatch(r"[A-Z0-9]*\d[A-Z0-9]*", toks[0]) and len(toks[0]) >= 7:
        return False                                  # a lone caps+digits token = Slack/ID, not a prompt
    # PII guard — don't auto-SURFACE someone else's email / phone / long digit run. (This is a
    # safe DEFAULT for arbitrary users; it never alters a prompt, it just won't select this one.)
    if re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}|\b\d{3}[\s.\-]?\d{3}[\s.\-]?\d{4}\b|\b\d{6,}\b', text, re.I):
        return False
    return True


def _open_in_browser(path):
    """Best-effort: pop the finished profile in the default browser. Silent if it can't
    (headless / SSH / CI) — we just fall back to printing the path. Pass --no-open to skip."""
    try:
        import webbrowser
        if webbrowser.open("file://" + os.path.abspath(path)):
            print("  opened profile.html in your browser (pass --no-open to skip)")
            return
    except Exception:
        pass
    print("  open it yourself:", path)
