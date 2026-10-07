"""paxel cursor: split out of the original single-file paxel.py."""

import glob
import json
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime

from px_base import CURSOR_DB, CURSOR_DIR, _canon_input, _canon_tool, _texts, strip_injections


def _cursor_jsonl_files():
    """All agent-transcripts JSONL files: main sessions AND subagent sidechains
    (…/agent-transcripts/<session>/subagents/<id>.jsonl — one glob level deeper)."""
    main_pat = os.path.join(CURSOR_DIR, "**", "agent-transcripts", "*", "*.jsonl")
    sub_pat = os.path.join(CURSOR_DIR, "**", "agent-transcripts", "*", "subagents", "*.jsonl")
    return glob.glob(main_pat, recursive=True) + glob.glob(sub_pat, recursive=True)


def _cursor_dedup(sources):
    """Prefer the SQLite copy of a Cursor session over its JSONL transcript.

    The same modern session exists in BOTH places with complementary data: SQLite
    bubbles carry per-event timestamps and tool error statuses (JSONL has neither),
    while the JSONL carries full tool inputs — edit old/new strings the SQLite params
    omit — and the workspace path (via the project folder slug). So JSONL files whose
    session id is already a composer in state.vscdb are dropped from the event stream,
    and a twin map {sessionId: {"cwd", "jsonl"}} is forwarded to the SQLite reader,
    which backfills cwd and churn-bearing edit inputs from the twin.
    Subagent sidechains exist only as JSONL and are always kept.
    Returns (filtered sources, twin map)."""
    if not any(fmt == "cursor-jsonl" for _, _, fmt in sources):
        return sources, {}
    sqlite_ids = _cursor_sqlite_composer_ids(CURSOR_DB)
    twins = {}
    out = []
    for entry in sources:
        src, fp, fmt = entry
        if fmt != "cursor-jsonl":
            out.append(entry)
            continue
        sid, cwd, is_sidechain = _cursor_jsonl_meta(fp)
        if is_sidechain or sid not in sqlite_ids:
            out.append(entry)
        else:
            twins[sid] = {"cwd": cwd, "jsonl": fp}
    return out, twins


def _cursor_sqlite_composer_ids(db_path):
    """Composer (session) UUIDs present in state.vscdb; empty set if unreadable."""
    if not db_path or not os.path.isfile(db_path):
        return set()
    conn = _cursor_open_sqlite(db_path)
    if conn is None:
        return set()
    try:
        rows = conn.execute(
            "SELECT key FROM cursorDiskKV WHERE key LIKE 'composerData:%'").fetchall()
        return {k.split(":", 1)[-1] for (k,) in rows}
    except Exception:
        return set()
    finally:
        conn.close()


# ---- Cursor: agent-transcripts JSONL + state.vscdb SQLite (deduped) ---------
# Keys are snake_case: the SQLite era uses snake_case names natively, and the modern
# JSONL CamelCase names (StrReplace, ReadLints, CallMcpTool, …) are snake_cased by
# _cursor_tool_name before lookup, so one table covers both generations.
_CURSOR_TOOL_MAP = {
    "run_terminal_command_v2": "Bash", "run_terminal_cmd": "Bash",
    "read_file_v2": "Read", "read_file": "Read",
    "edit_file_v2": "Edit", "edit_file": "Edit", "search_replace": "Edit",
    "str_replace": "Edit", "apply_patch": "Edit",
    "delete_file": "Edit", "delete": "Edit", "write_file": "Write",
    "glob_file_search": "Glob", "list_dir_v2": "Glob", "list_dir": "Glob",
    "ripgrep_raw_search": "Grep", "semantic_search_full": "Grep",
    "semantic_search": "Grep", "rg": "Grep",
    "web_search": "WebSearch", "web_fetch": "WebFetch",
    "task_v2": "Agent", "subagent": "Agent", "todo_write": "TodoWrite",
    "create_plan": "EnterPlanMode", "ask_question": "AskUserQuestion",
    "read_lints": "Read", "edit_notebook": "NotebookEdit",
    "await_shell": "BashOutput", "await": "BashOutput",
}

# Patch headers in an ApplyPatch payload, e.g. "*** Update File: src/foo.py"
_CURSOR_PATCH_FILE_RE = re.compile(r"^\*{3}\s*(?:Update|Add|Create|Delete)\s+File:\s*(.+)$", re.M)


def _cursor_project_cwd(project_slug):
    """Best-effort reverse of Cursor's project folder slug -> workspace path."""
    if not project_slug:
        return None
    norm = project_slug.replace("\\", "/")
    if norm.startswith("Users/") or norm.startswith("Users-"):
        return "/" + norm.replace("-", "/")
    if norm.startswith("home/") or norm.startswith("home-"):
        return "/" + norm.replace("-", "/")
    return None


def _cursor_jsonl_meta(fp):
    """Return (sessionId, cwd, is_sidechain) from an agent-transcripts path.
    Subagent transcripts (…/<session>/subagents/<id>.jsonl) attribute to the PARENT
    session id, mirroring Claude's sidechains-share-the-session semantics."""
    norm = fp.replace("\\", "/")
    sid = os.path.basename(fp).rsplit(".", 1)[0]
    is_sidechain = "/subagents/" in norm
    cwd = None
    parts = norm.split("/agent-transcripts/")
    if len(parts) == 2:
        proj = parts[0].rstrip("/").split("/")[-1]
        cwd = _cursor_project_cwd(proj)
        if is_sidechain:
            sid = parts[1].split("/")[0] or sid
    return sid, cwd, is_sidechain


# Harness-injected wrapper blocks that surround the human's words in Cursor JSONL user
# turns (attachments, skill manifests, linter dumps, …) — stripped so prompt length and
# the verbatim-quote cards reflect what the human actually typed.
_CURSOR_WRAPPER_RE = re.compile(
    r"<(attached_files|image_files|manually_attached_skills|available_skills|agent_skills|"
    r"external_links|code_selection|recently_viewed_files|open_and_recently_viewed_files|"
    r"linter_errors|system_notification|system_reminder|additional_data|user_info|"
    r"current_file|cursor_position|edit_history|timestamp)>.*?</\1>", re.S | re.I)


def _cursor_clean_prompt(text):
    if not text:
        return ""
    # The human-typed turn lives inside <user_query>…</user_query>; everything around it
    # is injected context. When the tag is present, keep ONLY its contents.
    found = re.findall(r"<user_query>(.*?)</user_query>", text, flags=re.S | re.I)
    if found:
        text = "\n".join(found)
    else:
        text = _CURSOR_WRAPPER_RE.sub("", text)
    return strip_injections(text).strip()


def _cursor_tool_key(name):
    """snake_case a Cursor tool name ('StrReplace' -> 'str_replace') for map lookup."""
    n = str(name or "tool")
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", n).lower().replace("-", "_")


def _cursor_tool_name(name):
    n = str(name or "tool")
    key = _cursor_tool_key(n)
    if key.startswith("mcp") and not key.startswith("mcp__"):
        return "mcp__" + n
    if n.startswith("mcp__"):
        return n
    mapped = _CURSOR_TOOL_MAP.get(key)
    if mapped:
        return mapped
    return _canon_tool(n)


def _cursor_tool_input(raw_name, raw):
    key = _cursor_tool_key(raw_name)
    if isinstance(raw, str):
        if key == "apply_patch":
            # ApplyPatch carries the raw patch text, not JSON — count it like Codex's
            # apply_patch (patch lines as added churn; diff markers over-count a bit).
            m = _CURSOR_PATCH_FILE_RE.search(raw)
            raw = {"new_string": raw, "old_string": "",
                   "file_path": m.group(1).strip() if m else ""}
        else:
            try:
                raw = json.loads(raw or "{}")
            except Exception:
                raw = {"raw": raw}
    if not isinstance(raw, dict):
        raw = {}
    cname = _cursor_tool_name(raw_name)
    inp = dict(raw)
    if cname == "Bash":
        inp.setdefault("command", inp.get("command") or "")
    elif cname in ("Read", "Write", "Edit", "MultiEdit"):
        fp = (inp.get("targetFile") or inp.get("file_path") or inp.get("path")
              or inp.get("filePath") or inp.get("relativeWorkspacePath"))
        if fp:
            inp["file_path"] = fp
        if cname == "Edit":
            inp.setdefault("new_string", inp.get("codeEdit") or inp.get("code")
                            or inp.get("new_string") or "")
            inp.setdefault("old_string", inp.get("old_string") or inp.get("oldString") or "")
        if cname == "Write":
            inp.setdefault("content", inp.get("contents") or inp.get("code") or "")
    return _canon_input(cname, inp)


def _cursor_tool(raw_name, raw_input):
    """Resolve a Cursor tool call to (canonical name, normalized input).
    CallMcpTool is special: the real MCP tool lives in the input (server/toolName),
    so it's renamed mcp__<server>__<tool> to count as an MCP call, not a native one."""
    inp = _cursor_tool_input(raw_name, raw_input)
    if _cursor_tool_key(raw_name) == "call_mcp_tool":
        server = str(inp.get("server") or "server")
        tool = str(inp.get("toolName") or inp.get("tool_name") or "tool")
        return f"mcp__{server}__{tool}", inp
    return _cursor_tool_name(raw_name), inp


def _cursor_jsonl_blocks(content):
    blocks = []
    if isinstance(content, str):
        if content:
            blocks.append({"type": "text", "text": content})
        return blocks
    if not isinstance(content, list):
        return blocks
    for part in content:
        if not isinstance(part, dict):
            continue
        pt = part.get("type")
        if pt == "text" and part.get("text"):
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif pt == "thinking":
            blocks.append({"type": "thinking",
                            "thinking": part.get("thinking") or part.get("text") or ""})
        elif pt in ("tool_use", "toolCall"):
            raw_inp = part.get("input") or part.get("arguments") or {}
            name, inp = _cursor_tool(part.get("name"), raw_inp)
            blocks.append({"type": "tool_use", "name": name, "input": inp})
        elif pt == "tool_result":
            blocks.append({"type": "tool_result",
                           "is_error": bool(part.get("is_error") or part.get("isError"))})
    return blocks


def _cursor_jsonl_events(fp):
    sid, cwd, is_sidechain = _cursor_jsonl_meta(fp)
    base = {"sessionId": sid, "cwd": cwd}
    if is_sidechain:
        base["isSidechain"] = True
    # Real Cursor JSONL carries NO per-event timestamps (the SQLite copy of the same
    # session does — and is preferred). For JSONL-only sessions, stamp the FIRST event
    # with the file mtime so the session still lands on the calendar / time window,
    # without flooding the hour histogram with thousands of identical fake timestamps.
    mtime_iso = None
    try:
        mtime_iso = datetime.fromtimestamp(os.path.getmtime(fp)).astimezone().isoformat()
    except Exception:
        pass
    first = True
    try:
        fh = open(fp, "r", encoding="utf-8", errors="replace")
    except Exception:
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                yield {"__bad__": True}
                continue
            if not isinstance(obj, dict):
                yield {"__bad__": True}
                continue
            role = obj.get("role")
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
            ts = obj.get("timestamp") or msg.get("timestamp")
            if ts is None and first:
                ts = mtime_iso
            content = msg.get("content")
            if role == "user":
                text = _cursor_clean_prompt(_texts(content))
                if text:
                    first = False
                    yield {**base, "type": "user", "timestamp": ts,
                           "message": {"role": "user", "content": text}}
            elif role == "assistant":
                blocks = _cursor_jsonl_blocks(content)
                tool_results = [b for b in blocks if b.get("type") == "tool_result"]
                blocks = [b for b in blocks if b.get("type") != "tool_result"]
                if blocks:
                    first = False
                    yield {**base, "type": "assistant", "timestamp": ts,
                           "message": {"role": "assistant", "model": msg.get("model"),
                                       "content": blocks}}
                if tool_results:
                    yield {**base, "type": "user", "timestamp": ts,
                           "message": {"role": "user", "content": tool_results}}
            elif role is None and obj.get("type") == "turn_ended":
                # status-only marker line; a failed turn is the closest thing the JSONL
                # format has to an API error signal ("aborted" = user stop, not an error)
                if str(obj.get("status") or "").lower() in ("error", "failed"):
                    yield {**base, "type": "system", "timestamp": ts,
                           "isApiErrorMessage": True}


def _cursor_bubble_blocks(bubble):
    blocks = []
    text = bubble.get("text") or ""
    if text:
        blocks.append({"type": "text", "text": text})
    for tb in bubble.get("allThinkingBlocks") or []:
        if isinstance(tb, dict):
            t = tb.get("text") or tb.get("thinking") or ""
            if t:
                blocks.append({"type": "thinking", "thinking": t})
        elif isinstance(tb, str) and tb:
            blocks.append({"type": "thinking", "thinking": tb})
    tfd = bubble.get("toolFormerData")
    tool_meta = None
    if isinstance(tfd, dict) and tfd.get("name"):
        name, inp = _cursor_tool(tfd.get("name"), tfd.get("params"))
        blocks.append({"type": "tool_use", "name": name, "input": inp})
        st = str(tfd.get("status") or "completed").lower()
        if st in ("error", "failed"):
            tool_meta = True
        elif st in ("completed", "success", "done"):
            tool_meta = False
        # cancelled / aborted / interrupted: user stopped it — neither success nor error
    return blocks, tool_meta


def _cursor_open_sqlite(db_path):
    try:
        return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return None


def _cursor_jsonl_edit_inputs(fp):
    """Per-tool FIFO queues of churn-bearing inputs (Edit/Write/MultiEdit) from a
    session's JSONL twin. The SQLite copy of the same session stores only the edited
    file's path in its tool params — the old/new strings live ONLY in the JSONL — so
    the SQLite reader pops these to backfill churn, pairing nth Edit with nth Edit."""
    queues = defaultdict(list)
    for ev in _cursor_jsonl_events(fp):
        msg = ev.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for b in content:
            if (isinstance(b, dict) and b.get("type") == "tool_use"
                    and b.get("name") in ("Edit", "Write", "MultiEdit")):
                queues[b["name"]].append(b.get("input") or {})
    return queues


def _cursor_sqlite_events(db_path, twins=None):
    conn = _cursor_open_sqlite(db_path)
    if conn is None:
        return
    twins = twins or {}
    try:
        rows = conn.execute(
            "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'"
        ).fetchall()
    except Exception:
        conn.close()
        return
    for key, val in rows:
        composer_id = key.split(":", 1)[-1]
        try:
            meta = json.loads(val)
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        headers = meta.get("fullConversationHeadersOnly") or []
        if not headers:
            continue
        # cwd comes from the JSONL twin's project slug — the DB stores no workspace path
        twin = twins.get(composer_id) or {}
        base = {"sessionId": composer_id, "cwd": twin.get("cwd")}
        edit_queues = _cursor_jsonl_edit_inputs(twin["jsonl"]) if twin.get("jsonl") else None
        for hdr in headers:
            if not isinstance(hdr, dict):
                continue
            bubble_id = hdr.get("bubbleId")
            if not bubble_id:
                continue
            bkey = f"bubbleId:{composer_id}:{bubble_id}"
            try:
                brow = conn.execute(
                    "SELECT value FROM cursorDiskKV WHERE key = ?", (bkey,)
                ).fetchone()
            except Exception:
                continue
            if not brow:
                continue
            try:
                bubble = json.loads(brow[0])
            except Exception:
                continue
            if not isinstance(bubble, dict):
                continue
            ts = bubble.get("createdAt")
            btype = hdr.get("type")
            if btype is None:
                btype = bubble.get("type")
            blocks, tool_err = _cursor_bubble_blocks(bubble)
            if edit_queues:
                for b in blocks:
                    if (b.get("type") == "tool_use" and b.get("name") in edit_queues
                            and not (b["input"].get("new_string") or b["input"].get("content")
                                     or b["input"].get("edits"))):
                        for k, v in edit_queues[b["name"]].pop(0).items():
                            if not b["input"].get(k):   # fill missing AND ""-normalized keys
                                b["input"][k] = v
                        if not edit_queues[b["name"]]:
                            del edit_queues[b["name"]]
            if btype == 1:
                text = _texts(blocks) or bubble.get("text") or ""
                if text:
                    yield {**base, "type": "user", "timestamp": ts,
                           "message": {"role": "user", "content": text}}
            elif btype == 2:
                if blocks:
                    yield {**base, "type": "assistant", "timestamp": ts,
                           "message": {"role": "assistant", "content": blocks}}
                if tool_err is not None:
                    yield {**base, "type": "user", "timestamp": ts,
                           "message": {"role": "user",
                                       "content": [{"type": "tool_result",
                                                    "is_error": bool(tool_err)}]}}
    conn.close()
