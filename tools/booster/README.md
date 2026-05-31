# Agent Booster

Cut AI coding agent token costs 5–15x by routing only the code that matters.

Instead of sending full source files to the model on every read, Agent Booster builds a symbol index of your codebase and returns only the functions and classes relevant to the current task.

---

## How it works

```
Without Booster                    With Booster
─────────────────                  ────────────────────────────
Read executor.py                   Read executor.py + task hint
→ 1,881 lines (~6k tokens)         → 3 matching functions (~200 tokens)
```

Five layers work together:

| Layer | What it does |
|---|---|
| **Symbol index** | tree-sitter parses every `.py` file, extracts functions/classes into SQLite |
| **Semantic diff** | only re-indexes files that changed since last run |
| **Smart read** | given a file + task description, returns only matching symbol line ranges |
| **MCP server** | exposes tools over stdio so any MCP-compatible agent can call them |
| **Platform init** | one command writes the right config for Claude Code, Cursor, or Codex |

---

## Installation

Requires Python 3.10+.

```bash
pip install -e tools/booster
```

Verify:

```bash
booster --help
```

---

## Quickstart

**Step 1 — Index your codebase**

Run once from your project root. Re-run after large refactors.

```bash
booster index
# Indexed 166 files, 1107 symbols.
```

The index is stored at `.booster/symbols.db` (SQLite, gitignored).

**Step 2 — Wire up your AI tool**

```bash
booster init claude    # Claude Code
booster init cursor    # Cursor
booster init codex     # OpenAI Codex CLI
booster init all       # print all three
```

Each command prints the JSON config snippet to paste into the right file. For Claude Code, copy the output into `.mcp.json` at your project root (or use the pre-wired `.mcp.json` already in this repo).

**Step 3 — Restart your AI tool**

The `agent-booster` MCP server will be available in every session. No further setup needed.

---

## CLI reference

```bash
booster index
```
Scans all `.py` files from the current directory, extracts functions and classes, stores in `.booster/symbols.db`. Skips `node_modules`, `.venv`, `__pycache__`, `.git`, `.booster`.

---

```bash
booster search "<query>"
```
Keyword search across all indexed symbols. Returns file path, line number, kind, name, and signature.

```bash
booster search "workflow execute"
# apps/api/app/runtime/executor.py:1165  function _execute_output  def _execute_output(...)
```

---

```bash
booster serve
```
Starts the MCP server over stdio. Claude Code, Cursor, and Codex connect to this automatically when configured via `booster init`.

---

```bash
booster init <platform>
```
Prints the MCP config snippet for the target platform. `platform` is one of: `claude`, `cursor`, `codex`, `all`.

---

```bash
booster gain
```
Shows token savings statistics from past sessions. (Full analytics in a future release — currently a stub.)

---

## MCP tools

Once `booster serve` is running, these tools are available to the agent:

### `get_symbols(file)`
Returns all indexed symbols for a file — name, kind, line range, and signature.

```
Input:  { "file": "apps/api/app/runtime/executor.py" }
Output: function run_workflow (lines 42-89): def run_workflow(...)
        class WorkflowState (lines 91-140): class WorkflowState:
        ...
```

### `search_context(task)`
Keyword search across all symbols in the index. Returns top 10 matches with file locations.

```
Input:  { "task": "authenticate user token" }
Output: apps/api/app/auth/middleware.py:34 function verify_token — def verify_token(...)
        ...
```

### `smart_read(file, task)`
Returns only the lines of a file that are relevant to the task. Falls back to full file content if no symbols match.

```
Input:  { "file": "apps/api/app/runtime/executor.py", "task": "execute output block" }
Output: # function _execute_output (lines 1165-1210)
        def _execute_output(block, state, credentials, ...):
            ...
```

---

## Platform config details

### Claude Code

Add to `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "agent-booster": {
      "command": "booster",
      "args": ["serve"]
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "agent-booster": {
      "command": "booster",
      "args": ["serve"]
    }
  }
}
```

### OpenAI Codex CLI

Add to `~/.codex/config.json`:

```json
{
  "mcp": {
    "servers": {
      "agent-booster": {
        "command": "booster",
        "args": ["serve"]
      }
    }
  }
}
```

---

## Where it fits

Agent Booster is the third layer in a three-layer token reduction stack — each layer is independent and addable separately:

```
Layer 3 — Agent Booster     AST+semantic routing, smart file reads
Layer 2 — RTK               Token compression on tool output
Layer 1 — Prompt caching    Stable context reuse (native to Claude Code + API)
```

---

## Project layout

```
tools/booster/
├── README.md
├── pyproject.toml
└── booster/
    ├── __init__.py
    ├── cli.py          # click commands: index, search, serve, init, gain
    ├── indexer.py      # tree-sitter parser + SQLite symbol store
    ├── retriever.py    # smart_read: task description → relevant line slice
    └── mcp_server.py   # MCP server exposing get_symbols, search_context, smart_read
```

---

## Roadmap

- [ ] TypeScript/TSX support (tree-sitter-typescript)
- [ ] Vector embeddings for semantic (not just keyword) search
- [ ] Smart model routing (`route_model` tool: Haiku / Sonnet / Opus)
- [ ] `booster gain` — real token savings analytics
- [ ] Watch mode: auto re-index on file save
- [ ] Publish to PyPI as `agent-booster`
