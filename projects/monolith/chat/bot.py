"""Discord bot -- gateway listener and message handler."""

import logging
import os

import discord

from chat.agent import create_agent, format_context_messages
from chat.embedding import EmbeddingClient
from chat.store import MessageStore
from app.db import get_engine

from sqlmodel import Session

logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")


def should_respond(message: discord.Message, bot_user: discord.User) -> bool:
    """Determine if the bot should respond to a message."""
    if message.author.bot:
        return False
    if bot_user in message.mentions:
        return True
    if (
        message.reference
        and hasattr(message.reference, "resolved")
        and message.reference.resolved
        and message.reference.resolved.author.id == bot_user.id
    ):
        return True
    return False


class ChatBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.embed_client = EmbeddingClient()
        self.agent = create_agent()

    async def on_ready(self):
        logger.info("Discord bot connected as %s", self.user)

    async def on_message(self, message: discord.Message):
        # Always store messages (for memory)
        try:
            with Session(get_engine()) as session:
                store = MessageStore(session=session, embed_client=self.embed_client)
                await store.save_message(
                    discord_message_id=str(message.id),
                    channel_id=str(message.channel.id),
                    user_id=str(message.author.id),
                    username=message.author.display_name,
                    content=message.content,
                    is_bot=message.author.bot,
                )
        except Exception:
            logger.exception("Failed to store message %s", message.id)

        if not should_respond(message, self.user):
            return

        try:
            async with message.channel.typing():
                response_text = await self._generate_response(message)
            sent = await message.reply(response_text)

            # Store bot response
            with Session(get_engine()) as session:
                store = MessageStore(session=session, embed_client=self.embed_client)
                await store.save_message(
                    discord_message_id=str(sent.id),
                    channel_id=str(message.channel.id),
                    user_id=str(self.user.id),
                    username=self.user.display_name,
                    content=response_text,
                    is_bot=True,
                )
        except Exception:
            logger.exception("Failed to respond to message %s", message.id)

    async def _generate_response(self, message: discord.Message) -> str:
        """Build context and run the PydanticAI agent."""
        with Session(get_engine()) as session:
            store = MessageStore(session=session, embed_client=self.embed_client)

            # Recent window
            recent = store.get_recent(str(message.channel.id), limit=20)
            recent_ids = [m.id for m in recent if m.id is not None]

            # Semantic recall
            query_embedding = await self.embed_client.embed(message.content)
            similar = store.search_similar(
                channel_id=str(message.channel.id),
                query_embedding=query_embedding,
                limit=5,
                exclude_ids=recent_ids,
            )

        # Build context
        context_parts = []
        if similar:
            context_parts.append(
                "Relevant older messages:\n" + format_context_messages(similar)
            )
        context_parts.append("Recent conversation:\n" + format_context_messages(recent))
        context = "\n\n---\n\n".join(context_parts)

        # Run agent
        user_prompt = (
            f"{context}\n\nCurrent message from "
            f"{message.author.display_name}: {message.content}"
        )
        result = await self.agent.run(user_prompt)
        return result.output


def create_bot() -> ChatBot:
    """Factory function for the Discord bot."""
    return ChatBot()
