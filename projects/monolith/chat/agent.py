"""PydanticAI agent -- assembles context and runs Gemma with tool calling."""

import os
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from chat.embedding import EmbeddingClient
from chat.models import Attachment, Message
from chat.store import MessageStore
from chat.web_search import search_web

LLAMA_CPP_URL = os.environ.get("LLAMA_CPP_URL", "")


@dataclass
class ChatDeps:
    channel_id: str
    store: MessageStore
    embed_client: EmbeddingClient


def build_system_prompt() -> str:
    """Build the system prompt for the chat agent."""
    return (
        "You are a helpful assistant in a Discord chat. "
        "You have access to these tools:\n"
        "- web_search: Look up current information from the web.\n"
        "- search_history: Search older messages in this channel by topic, "
        "optionally filtered by username. Use when the recent conversation "
        "doesn't have enough context.\n"
        "- get_user_summary: Get a summary of what a specific user has been "
        "discussing in this channel. Use when asked about a user's activity.\n\n"
        "Keep responses concise and conversational. "
        "You can see recent conversation history for context. "
        "Use your tools before saying you don't have context."
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


def create_agent(base_url: str | None = None) -> Agent[ChatDeps]:
    """Create a PydanticAI agent configured for Gemma via llama.cpp."""
    url = base_url or LLAMA_CPP_URL

    model = OpenAIChatModel(
        "gemma-4-26b-a4b",
        provider=OpenAIProvider(
            base_url=f"{url}/v1",
            api_key="not-needed",
        ),
    )

    agent: Agent[ChatDeps] = Agent(
        model,
        system_prompt=build_system_prompt(),
    )

    @agent.tool_plain
    async def web_search(query: str) -> str:
        """Search the web for current information. Use this for recent events, facts, or anything that needs up-to-date data."""
        return await search_web(query)

    @agent.tool
    async def search_history(
        ctx: RunContext[ChatDeps],
        query: str,
        username: str | None = None,
        limit: int = 5,
    ) -> str:
        """Search older messages in this channel by topic. Optionally filter by username."""
        deps = ctx.deps
        query_embedding = await deps.embed_client.embed(query)
        user_id = None
        if username:
            user_id = deps.store.find_user_id_by_username(deps.channel_id, username)
        results = deps.store.search_similar(
            channel_id=deps.channel_id,
            query_embedding=query_embedding,
            limit=limit,
            user_id=user_id,
        )
        if not results:
            return "No matching messages found."
        return format_context_messages(results)

    @agent.tool
    async def get_user_summary(
        ctx: RunContext[ChatDeps],
        username: str,
    ) -> str:
        """Get a summary of what a user has been discussing in this channel."""
        deps = ctx.deps
        summary = deps.store.get_user_summary(deps.channel_id, username)
        if not summary:
            return f"No summary available for {username}."
        return (
            f"Summary for {username} "
            f"(updated {summary.updated_at.strftime('%Y-%m-%d')}):\n"
            f"{summary.summary}"
        )

    return agent
