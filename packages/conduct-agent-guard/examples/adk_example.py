"""Google ADK + Conduct. Uses Claude via ADK's LiteLlm wrapper, so it needs ANTHROPIC_API_KEY
(or swap in model="gemini-2.5-flash" with GOOGLE_API_KEY) and CONDUCT_AGENT_TOKEN.

    pip install "conduct-agent-guard[adk]" litellm
    python examples/adk_example.py
"""
import asyncio

from _demo import MODEL, PROVIDER, PROMPT, SYSTEM, memory_save, search_web
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from conduct_agent_guard.adk import conduct_before_tool_callback

agent = LlmAgent(
    name="support",
    model=LiteLlm(model=f"{PROVIDER}/{MODEL}"),
    instruction=SYSTEM,
    tools=[search_web, memory_save],
    before_tool_callback=conduct_before_tool_callback(),  # ← Conduct
)


async def main() -> None:
    runner = InMemoryRunner(agent=agent, app_name="demo")
    session = await runner.session_service.create_session(app_name="demo", user_id="u1")
    msg = types.Content(role="user", parts=[types.Part(text=PROMPT)])
    async for event in runner.run_async(user_id="u1", session_id=session.id, new_message=msg):
        if event.is_final_response() and event.content and event.content.parts:
            print(event.content.parts[0].text)


asyncio.run(main())
