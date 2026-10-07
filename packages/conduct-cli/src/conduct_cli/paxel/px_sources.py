"""paxel sources: split out of the original single-file paxel.py."""

import glob
import json
import os

from px_base import BASE, CODEX_DIR, CURSOR_DB, CURSOR_DIR, GEMINI_DIR, OPENCODE_DIR, PI_DIR, _canon_input, _canon_tool, _iso_ms, _texts
from px_cursor import _cursor_jsonl_events, _cursor_jsonl_files, _cursor_sqlite_events


def discover_sources(selected):
    out = []
    if "claude" in selected and os.path.isdir(BASE):
        for fp in sorted(glob.glob(os.path.join(BASE, "**", "*.jsonl"), recursive=True)):
            out.append(("claude", fp, "claude"))
    if "codex" in selected and os.path.isdir(CODEX_DIR):
        for fp in sorted(glob.glob(os.path.join(CODEX_DIR, "**", "*.jsonl"), recursive=True)):
            out.append(("codex", fp, "codex"))
    if "gemini" in selected and os.path.isdir(GEMINI_DIR):
        for fp in sorted(glob.glob(os.path.join(GEMINI_DIR, "**", "*.json"), recursive=True)):
            out.append(("gemini", fp, "gemini"))
    if "pi" in selected and os.path.isdir(PI_DIR):
        for fp in sorted(glob.glob(os.path.join(PI_DIR, "**", "*.jsonl"), recursive=True)):
            out.append(("pi", fp, "pi"))
    if "opencode" in selected and os.path.isdir(OPENCODE_DIR):
        session_glob = os.path.join(OPENCODE_DIR, "storage", "session", "*", "*.json")
        for fp in sorted(glob.glob(session_glob)):
            out.append(("opencode", fp, "opencode"))
    if "cursor" in selected and os.path.isdir(CURSOR_DIR):
        for fp in sorted(_cursor_jsonl_files()):
            out.append(("cursor", fp, "cursor-jsonl"))
    if "cursor" in selected and os.path.isfile(CURSOR_DB):
        out.append(("cursor", CURSOR_DB, "cursor-sqlite"))
    return out


def iter_events(fp, fmt, cursor_twins=None):
    """Yield Claude-shaped event dicts for any supported source format."""
    if fmt == "claude":
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
                yield obj if isinstance(obj, dict) else {"__bad__": True}
    elif fmt == "codex":
        yield from _codex_events(fp)
    elif fmt == "gemini":
        yield from _gemini_events(fp)
    elif fmt == "pi":
        yield from _pi_events(fp)
    elif fmt == "opencode":
        yield from _opencode_events(fp)
    elif fmt == "cursor-jsonl":
        yield from _cursor_jsonl_events(fp)
    elif fmt == "cursor-sqlite":
        yield from _cursor_sqlite_events(fp, cursor_twins)


def _codex_tool(p):
    """Map a Codex tool/function call to a Claude-shaped (name, input) tool_use."""
    pt = p.get("type")
    if pt == "web_search_call":
        return "WebSearch", {}
    name = p.get("name") or pt or "tool"
    try:
        args = json.loads(p.get("arguments") or "{}")
    except Exception:
        args = {}
    if not isinstance(args, dict):
        args = {}
    if pt == "local_shell_call" or name in ("exec_command", "shell", "local_shell", "bash"):
        return "Bash", {"command": args.get("cmd") or args.get("command") or str(p.get("action") or "")}
    if name in ("apply_patch", "patch", "edit_file", "write_file", "create_file"):
        return "Edit", {"new_string": args.get("patch") or args.get("content") or "",
                        "old_string": "", "file_path": args.get("path") or args.get("file") or ""}
    return name, args


def _codex_events(fp):
    rows = []
    try:
        for line in open(fp, "r", encoding="utf-8", errors="replace"):
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except Exception:
        return
    sid = os.path.basename(fp).split(".")[0]
    cwd = None
    for ev in rows:                       # first pass: session id + working dir
        p = ev.get("payload") or {}
        if ev.get("type") == "session_meta":
            sid = p.get("id") or sid
            cwd = p.get("cwd") or cwd
        elif ev.get("type") == "response_item" and p.get("type") == "function_call":
            try:
                a = json.loads(p.get("arguments") or "{}")
                cwd = cwd or (a.get("workdir") if isinstance(a, dict) else None)
            except Exception:
                pass
    base = {"sessionId": sid, "cwd": cwd}
    for ev in rows:
        if ev.get("type") != "response_item":
            continue
        ts = ev.get("timestamp")
        p = ev.get("payload") or {}
        pt = p.get("type")
        if pt == "message":
            role = p.get("role")
            text = _texts(p.get("content"))
            if role == "user" and text:
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": text}}
            elif role == "assistant":
                yield {**base, "type": "assistant", "timestamp": ts,
                       "message": {"role": "assistant",
                                   "content": [{"type": "text", "text": text}] if text else []}}
            # developer/system messages are tooling, not human prompts → skipped
        elif pt == "reasoning":
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant",
                               "content": [{"type": "thinking",
                                            "thinking": _texts(p.get("content")) or p.get("summary") or ""}]}}
        elif pt in ("function_call", "local_shell_call", "custom_tool_call", "web_search_call"):
            name, inp = _codex_tool(p)
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant",
                               "content": [{"type": "tool_use", "name": name, "input": inp}]}}
        elif pt == "function_call_output":
            out = p.get("output")
            is_err = isinstance(out, dict) and out.get("success") is False
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user",
                               "content": [{"type": "tool_result", "is_error": bool(is_err)}]}}


def _gemini_events(fp):
    try:
        d = json.load(open(fp, "r", encoding="utf-8", errors="replace"))
    except Exception:
        return
    if not isinstance(d, dict):
        return
    base = {"sessionId": d.get("sessionId") or os.path.basename(fp), "cwd": None}
    for m in d.get("messages") or []:
        if not isinstance(m, dict):
            continue
        ts = m.get("timestamp")
        role = m.get("type") or m.get("role")
        content = m.get("content")
        text = _texts(content)
        if role == "user" and text:
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user", "content": text}}
        elif role in ("gemini", "model", "assistant"):
            blocks = [{"type": "text", "text": text}] if text else []
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("functionCall"), dict):
                        fc = part["functionCall"]
                        blocks.append({"type": "tool_use", "name": fc.get("name", "tool"),
                                       "input": fc.get("args") if isinstance(fc.get("args"), dict) else {}})
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant", "content": blocks}}


def _pi_blocks(content):
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
            blocks.append({"type": "thinking", "thinking": part.get("thinking") or part.get("text") or ""})
        elif pt in ("toolCall", "tool_use"):
            name = _canon_tool(part.get("name"))
            inp = part.get("arguments") or part.get("input") or {}
            blocks.append({"type": "tool_use", "name": name, "input": _canon_input(name, inp)})
        elif pt == "tool_result":
            blocks.append({"type": "tool_result", "is_error": bool(part.get("is_error") or part.get("isError"))})
    return blocks


def _pi_events(fp):
    sid, cwd = os.path.basename(fp).split(".")[0], None
    try:
        rows = [json.loads(line) for line in open(fp, "r", encoding="utf-8", errors="replace") if line.strip()]
    except Exception:
        return
    for obj in rows:
        if isinstance(obj, dict) and obj.get("type") == "session":
            sid = obj.get("id") or sid
            cwd = obj.get("cwd") or cwd
            break
    base = {"sessionId": sid, "cwd": cwd}
    for obj in rows:
        if not isinstance(obj, dict) or obj.get("type") != "message":
            continue
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        role = msg.get("role")
        ts = obj.get("timestamp") or _iso_ms(msg.get("timestamp"))
        if role == "user":
            text = _texts(msg.get("content"))
            if text:
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": text}}
        elif role == "assistant":
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant", "model": msg.get("model"),
                               "content": _pi_blocks(msg.get("content"))}}
        elif role == "toolResult":
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user",
                               "content": [{"type": "tool_result", "is_error": bool(msg.get("isError"))}]}}


def _opencode_events(fp):
    try:
        sess = json.load(open(fp, "r", encoding="utf-8", errors="replace"))
    except Exception:
        return
    if not isinstance(sess, dict):
        return
    sid = sess.get("id") or os.path.basename(fp).split(".")[0]
    cwd = sess.get("directory")
    msg_dir = os.path.join(OPENCODE_DIR, "storage", "message", sid)
    part_root = os.path.join(OPENCODE_DIR, "storage", "part")
    messages = []
    for mp in sorted(glob.glob(os.path.join(msg_dir, "*.json"))):
        try:
            m = json.load(open(mp, "r", encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if isinstance(m, dict):
            messages.append(m)
    messages.sort(key=lambda m: (m.get("time") or {}).get("created") or 0)
    base = {"sessionId": sid, "cwd": cwd}
    for m in messages:
        mid = m.get("id")
        ts = _iso_ms((m.get("time") or {}).get("created"))
        parts = []
        for pp in sorted(glob.glob(os.path.join(part_root, str(mid), "*.json"))):
            try:
                p = json.load(open(pp, "r", encoding="utf-8", errors="replace"))
            except Exception:
                continue
            if isinstance(p, dict):
                parts.append(p)
        parts.sort(key=lambda p: ((p.get("time") or {}).get("start") or 0, p.get("id") or ""))
        if m.get("role") == "user":
            texts = [p.get("text") for p in parts if p.get("type") == "text" and p.get("text")]
            if not texts:
                summ = m.get("summary") if isinstance(m.get("summary"), dict) else {}
                texts = [x for x in (summ.get("title"), summ.get("body")) if x]
            if texts:
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": "\n".join(texts)}}
        elif m.get("role") == "assistant":
            blocks, tool_results = [], []
            for p in parts:
                pt = p.get("type")
                if pt == "text" and p.get("text"):
                    blocks.append({"type": "text", "text": p.get("text", "")})
                elif pt == "reasoning":
                    blocks.append({"type": "thinking", "thinking": p.get("text", "")})
                elif pt == "tool":
                    st = p.get("state") if isinstance(p.get("state"), dict) else {}
                    name = _canon_tool(p.get("tool"))
                    inp = _canon_input(name, st.get("input") if isinstance(st.get("input"), dict) else {})
                    blocks.append({"type": "tool_use", "name": name, "input": inp})
                    is_err = st.get("status") not in (None, "completed") or bool(st.get("error"))
                    tool_results.append({"type": "tool_result", "is_error": is_err})
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant", "model": m.get("modelID"), "content": blocks}}
            if tool_results:
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": tool_results}}
