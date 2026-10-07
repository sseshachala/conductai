# conduct-agent-guard

Conduct Guard on every tool call, in the agent framework you already use. One line per framework; the same Conduct policy decides for all of them.

| Framework | One line |
|---|---|
| Claude Agent SDK | `ClaudeAgentOptions(hooks=conduct_hooks())` |
| OpenAI Agents SDK | `Agent(tools=guard_tools([...]))` |
| LangChain / LangGraph | `create_agent(..., middleware=[ConductMiddleware()])` |
| Google ADK | `LlmAgent(before_tool_callback=conduct_before_tool_callback())` |
| CrewAI | `register_conduct_hook()` before `crew.kickoff()` |

Each adapter sends the tool name + arguments to Conduct's `guard_check` action gate before the tool runs. **Adapters translate; Conduct decides.**

- `block` / `approval`: the tool does not run, and the model gets the reason (so it can explain or adapt).
- `warning` / `advisory`: the tool runs.

The audit row records which framework made the call.

```bash
pip install "conduct-agent-guard[claude]"     # or [openai] [langchain] [adk] [crewai]
export CONDUCT_AGENT_TOKEN=cond_agt_...       # from the Conduct console or `conduct login`
```

| Env var | Default |
|---|---|
| `CONDUCT_AGENT_TOKEN` | required |
| `CONDUCT_API_URL` | `https://gateway.conductai.ai` |
| `CONDUCT_WORKSPACE_ID` | from the token |

Unreachable Conduct fails closed (the tool is blocked); pass `ToolGuard(..., unreachable_fallback="fail_open")` to change that.

## Run the examples

Every example runs the same scenario. The agent searches the web (allowed), then tries to save the untrusted result to long-term memory. That save is **blocked** by the memory-poisoning rule (`asi06_untrusted_promotion_to_durable`) in a default Conduct workspace.

```bash
cd packages/conduct-agent-guard/examples
./run_all.sh            # live_smoke + all five agents
./run_all.sh smoke      # no LLM needed: every adapter against your live policy
./run_all.sh claude crewai
```

`run_all.sh` needs [`uv`](https://docs.astral.sh/uv/) and gives each framework its own environment. Current CrewAI and OpenAI Agents can't share one: they pin different `openai` majors.

### LLM access

The agent examples default to Anthropic (`claude-haiku-4-5`).

- **Direct:** `export ANTHROPIC_API_KEY=...`. The Claude Agent SDK example can also use your Claude Code login.
- **Through the Conduct Gateway** (model traffic governed too):

  ```bash
  # Anthropic profile
  export ANTHROPIC_BASE_URL=https://gateway.conductai.ai/gateway/v1/anthropic
  export ANTHROPIC_API_KEY=<conduct token>
  export DEMO_PROVIDER=anthropic DEMO_MODEL=cond-<code>-<alias>

  # or an OpenAI profile
  export OPENAI_BASE_URL=https://gateway.conductai.ai/gateway/v1/openai/v1
  export OPENAI_API_KEY=<conduct token>
  export DEMO_PROVIDER=openai DEMO_MODEL=cond-<code>-<alias>
  ```

  The profile identifier is on the Gateway profile page. `source ~/.conduct/env` sets the base URLs and keys if you used `conduct login`.

## Tests

```bash
uv run --no-project --with-editable '.[claude,openai,langchain,adk,dev]' pytest
uv run --no-project --with-editable '.[crewai,dev]' pytest     # CrewAI needs its own env
```

The core tests run without any framework installed; adapter tests skip when their SDK is missing.
