"""PydanticAI agent -- assembles context and runs Gemma with tool calling."""

import os

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from chat.models import Attachment, Message
from chat.web_search import search_web

LLAMA_CPP_URL = os.environ.get("LLAMA_CPP_URL", "")


def build_system_prompt() -> str:
    """Build the system prompt for the chat agent."""
    return (
        "You are a helpful assistant in a Discord chat. "
        "You have access to a web_search tool to look up current information. "
        "Use it when users ask about recent events, facts you're unsure about, "
        "or anything that benefits from up-to-date information. "
        "Keep responses concise and conversational. "
        "You can see recent conversation history and relevant older messages for context."
    )


def format_context_messages(
    messages: list[Message],
    attachments_by_msg: dict[int, list[Attachment]] | None = None,
) -> str:
    """Format a list of messages into a context string for the prompt."""
    att_map = attachments_by_msg or {}
    lines = []
    for msg in messages:
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
        if msg.is_bot:
            lines.append(f"[{timestamp}] Assistant: {msg.content}")
        else:
            lines.append(f"[{timestamp}] {msg.username}: {msg.content}")
        # Append image descriptions if present
        for att in att_map.get(msg.id, []):
            lines.append(f"  [Image: {att.description}]")
    return "\n".join(lines)


def create_agent(base_url: str | None = None) -> Agent:
    """Create a PydanticAI agent configured for Gemma via llama.cpp."""
    url = base_url or LLAMA_CPP_URL

    model = OpenAIChatModel(
        "gemma-4-26b-a4b",
        provider=OpenAIProvider(
            base_url=f"{url}/v1",
            api_key="not-needed",
        ),
    )

    agent = Agent(
        model,
        system_prompt=build_system_prompt(),
    )

    @agent.tool_plain
    async def web_search(query: str) -> str:
        """Search the web for current information. Use this for recent events, facts, or anything that needs up-to-date data."""
        return await search_web(query)

    return agent
