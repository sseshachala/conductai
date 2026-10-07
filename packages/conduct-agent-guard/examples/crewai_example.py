"""CrewAI + Conduct. Needs ANTHROPIC_API_KEY and CONDUCT_AGENT_TOKEN.

    pip install "conduct-agent-guard[crewai]" "crewai[anthropic]"   # "crewai[litellm]" for Gateway cond-* model ids
    python examples/crewai_example.py
"""
from _demo import MODEL, PROVIDER, PROMPT, SYSTEM, memory_save, search_web
from crewai import Agent, Crew, Task
from crewai.tools import tool

from conduct_agent_guard.crewai import register_conduct_hook

register_conduct_hook()  # ← Conduct: checks every tool call in every crew

agent = Agent(
    role="Support agent",
    goal=SYSTEM,
    backstory="Follows instructions exactly.",
    tools=[tool("search_web")(search_web), tool("memory_save")(memory_save)],
    llm=f"{PROVIDER}/{MODEL}",
)
task = Task(description=PROMPT, expected_output="Which steps succeeded or were blocked.", agent=agent)
print(Crew(agents=[agent], tasks=[task]).kickoff())
