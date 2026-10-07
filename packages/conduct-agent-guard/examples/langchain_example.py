"""LangChain (create_agent / LangGraph) + Conduct. Needs ANTHROPIC_API_KEY and CONDUCT_AGENT_TOKEN.

    pip install "conduct-agent-guard[langchain]" langchain-anthropic   # or langchain-openai
    python examples/langchain_example.py
"""
from _demo import MODEL, PROVIDER, PROMPT, SYSTEM, memory_save, search_web
from langchain.agents import create_agent

from conduct_agent_guard.langchain import ConductMiddleware

agent = create_agent(
    f"{PROVIDER}:{MODEL}",
    tools=[search_web, memory_save],
    system_prompt=SYSTEM,
    middleware=[ConductMiddleware()],  # ← Conduct
)

result = agent.invoke({"messages": [{"role": "user", "content": PROMPT}]})
print(result["messages"][-1].content)
