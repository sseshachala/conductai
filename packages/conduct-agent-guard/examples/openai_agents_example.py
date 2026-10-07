"""OpenAI Agents SDK + Conduct. Needs ANTHROPIC_API_KEY and CONDUCT_AGENT_TOKEN
(any LiteLLM model works; drop LitellmModel to use OpenAI with OPENAI_API_KEY).

    pip install "conduct-agent-guard[openai]" "openai-agents[litellm]"
    python examples/openai_agents_example.py
"""
from _demo import MODEL, PROVIDER, PROMPT, SYSTEM, memory_save, search_web
from agents import Agent, Runner, function_tool, set_tracing_disabled
from agents.extensions.models.litellm_model import LitellmModel

from conduct_agent_guard.openai_agents import guard_tools

# The SDK uploads traces to OpenAI by default, outside your Gateway. Off for a governed demo.
set_tracing_disabled(True)

agent = Agent(
    name="support",
    instructions=SYSTEM,
    model=LitellmModel(model=f"{PROVIDER}/{MODEL}"),
    tools=guard_tools([function_tool(search_web), function_tool(memory_save)]),  # ← Conduct
)

print(Runner.run_sync(agent, PROMPT).final_output)
