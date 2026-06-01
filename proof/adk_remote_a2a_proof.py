"""Proof: consume the Workoflow A2A server as a Google ADK ``RemoteA2aAgent``.

This is the exact A2A client path Gemini / Google ADK / Vertex use, so a pass
proves those platforms can consume us. Auth is injected via the ``httpx_client``
(the reliable seam - same lesson as ``workoflow-orchestrator``'s outbound A2A).

Install the proof extra first::

    pip install -e '.[proof]'

Run::

    A2A_CARD_URL=http://localhost:9008/.well-known/agent-card.json \
    TOKEN=<personal-access-token> \
    python proof/adk_remote_a2a_proof.py "Who knows Kubernetes?"
"""

import asyncio
import os
import sys

import httpx
from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.runners import InMemoryRunner
from google.genai import types


class BearerAuth(httpx.Auth):
    """Attach the Workoflow personal access token as a bearer credential."""

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


async def main(prompt: str) -> None:
    card_url = os.environ.get(
        "A2A_CARD_URL", "http://localhost:9008/.well-known/agent-card.json"
    )
    token = os.environ["TOKEN"]

    httpx_client = httpx.AsyncClient(
        auth=BearerAuth(token),
        timeout=httpx.Timeout(600.0, connect=10.0),
        follow_redirects=True,
    )

    remote = RemoteA2aAgent(
        name="workoflow_bot",
        agent_card=card_url,
        description="The Workoflow organizational AI agent (A2A).",
        httpx_client=httpx_client,
    )

    # A thin local agent that simply delegates to the remote Workoflow agent.
    root = LlmAgent(
        name="proof_root",
        model="gemini-2.0-flash",
        instruction="Delegate every user request to the workoflow_bot sub-agent.",
        sub_agents=[remote],
    )

    runner = InMemoryRunner(agent=root, app_name="a2a-proof")
    session = await runner.session_service.create_session(
        app_name="a2a-proof", user_id="proof-user"
    )

    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    async for event in runner.run_async(
        user_id="proof-user", session_id=session.id, new_message=content
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    print(part.text, end="", flush=True)
    print()
    await httpx_client.aclose()


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Who can help me with Kubernetes?"
    asyncio.run(main(prompt))
