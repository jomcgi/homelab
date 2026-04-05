"""Discord bot -- gateway listener and message handler."""

import asyncio
import hashlib
import logging
import os

import discord
import httpx
from pydantic_ai.messages import ModelResponse, ThinkingPart

from chat.agent import create_agent, format_context_messages
from chat.embedding import EmbeddingClient
from chat.store import MessageStore
from chat.vision import VisionClient
from app.db import get_engine

from sqlmodel import Session

logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_MESSAGE_LIMIT = 2000
THINKING_TRUNCATE_AT = 1985
LLAMA_CPP_URL = os.environ.get("LLAMA_CPP_URL", "")

LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY = 1.0  # seconds


def _extract_thinking(result) -> str | None:
    """Extract thinking text from PydanticAI ThinkingPart messages.

    llama.cpp returns reasoning in the ``reasoning_content`` field of the
    OpenAI-compatible response.  PydanticAI maps this to ``ThinkingPart``
    objects automatically.  Returns the concatenated thinking text, or
    None when no thinking was produced.
    """
    parts: list[str] = []
    for msg in result.new_messages():
        if not isinstance(msg, ModelResponse):
            continue
        for part in msg.parts:
            if isinstance(part, ThinkingPart) and part.content:
                parts.append(part.content.strip())
    return "\n\n".join(parts) if parts else None


async def _summarize_thinking(
    thinking: str,
    base_url: str | None = None,
) -> str:
    """Summarize thinking text if it exceeds Discord's message limit."""
    if len(thinking) <= DISCORD_MESSAGE_LIMIT:
        return thinking

    url = base_url or LLAMA_CPP_URL
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                f"{url}/v1/chat/completions",
                json={
                    "model": "gemma-4-26b-a4b",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Summarize this reasoning concisely. "
                                "Keep the key points but make it much shorter:\n\n"
                                f"{thinking}"
                            ),
                        }
                    ],
                    "max_tokens": 1024,
                },
            )
            resp.raise_for_status()
            summary = resp.json()["choices"][0]["message"]["content"]
            if len(summary) > DISCORD_MESSAGE_LIMIT:
                return summary[:THINKING_TRUNCATE_AT] + "... (truncated)"
            return summary
    except Exception:
        logger.warning("Failed to summarize thinking, truncating")
        return thinking[:THINKING_TRUNCATE_AT] + "... (truncated)"


class ThinkingView(discord.ui.View):
    """Discord View with a 'Show thinking' button that reveals model reasoning."""

    def __init__(self, thinking_text: str):
        super().__init__(timeout=None)
        self.thinking_text = thinking_text

    @discord.ui.button(label="Show thinking", style=discord.ButtonStyle.secondary)
    async def show_thinking(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(self.thinking_text, ephemeral=True)


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


async def download_image_attachments(
    attachments: list[discord.Attachment],
    vision_client: VisionClient,
    store: MessageStore | None = None,
) -> list[dict]:
    """Download image attachments and describe them with Gemma 4 vision.

    When a store is provided, checks for an existing blob by content hash
    and reuses its description instead of calling the vision model again.
    """
    results = []
    for att in attachments:
        if not att.content_type or not att.content_type.startswith("image/"):
            continue
        try:
            data = await att.read()
            sha = hashlib.sha256(data).hexdigest()
            existing = store.get_blob(sha) if store else None
            if existing:
                description = existing.description
                logger.info("Blob cache hit for %s (%s)", att.filename, sha[:12])
            else:
                description = await vision_client.describe(data, att.content_type)
            results.append(
                {
                    "data": data,
                    "content_type": att.content_type,
                    "filename": att.filename,
                    "description": description,
                }
            )
        except Exception:
            logger.exception("Failed to process attachment %s", att.filename)
    return results


class ChatBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.embed_client = EmbeddingClient()
        self.vision_client = VisionClient()
        self.agent = create_agent()

    async def on_ready(self):
        logger.info("Discord bot connected as %s", self.user)

    async def on_message(self, message: discord.Message):
        # Skip own messages — bot responses are stored explicitly after sending
        if message.author.id == self.user.id:
            return

        # Default to empty list so `attachments` is always bound even if the
        # store block raises before download_image_attachments() is called.
        attachments: list[dict] = []

        # Process image attachments (pass store for blob dedup)
        try:
            with Session(get_engine()) as session:
                store = MessageStore(session=session, embed_client=self.embed_client)
                attachments = await download_image_attachments(
                    message.attachments, self.vision_client, store=store
                )
                await store.save_message(
                    discord_message_id=str(message.id),
                    channel_id=str(message.channel.id),
                    user_id=str(message.author.id),
                    username=message.author.display_name,
                    content=message.content,
                    is_bot=message.author.bot,
                    attachments=attachments if attachments else None,
                )
        except Exception:
            logger.exception("Failed to store message %s", message.id)

        if not should_respond(message, self.user):
            return

        try:
            async with message.channel.typing():
                response_text, thinking = await self._generate_response(
                    message, attachments
                )
            if thinking:
                sent = await message.reply(response_text, view=ThinkingView(thinking))
            else:
                sent = await message.reply(response_text)
        except Exception:
            logger.exception("Failed to respond to message %s", message.id)
            try:
                await message.reply(
                    "Sorry, I'm having trouble reaching the language model right now. "
                    "Please try again in a moment."
                )
            except Exception:
                logger.exception(
                    "Failed to send error reply for message %s", message.id
                )
            return

        # Store bot response separately — a storage failure shouldn't
        # trigger an error reply when the user already received an answer.
        try:
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
            logger.exception("Failed to store bot response for message %s", message.id)

    async def _generate_response(
        self,
        message: discord.Message,
        current_attachments: list[dict] | None = None,
    ) -> tuple[str, str | None]:
        """Build context and run the PydanticAI agent.

        Returns (response_text, thinking_text). thinking_text is None when
        the model produced no thinking.
        """
        from chat.agent import ChatDeps

        with Session(get_engine()) as session:
            store = MessageStore(session=session, embed_client=self.embed_client)

            # Recent window only — semantic recall is now on-demand via tools
            recent = store.get_recent(str(message.channel.id), limit=20)

            # Run agent with deps so tools can access store + embeddings
            deps = ChatDeps(
                channel_id=str(message.channel.id),
                store=store,
                embed_client=self.embed_client,
            )

            # Load attachments for recent messages
            all_msg_ids = [m.id for m in recent if m.id is not None]
            attachments_by_msg = store.get_attachments(all_msg_ids)

            context = "Recent conversation:\n" + format_context_messages(
                recent, attachments_by_msg
            )

            user_prompt = (
                f"{context}\n\nCurrent message from "
                f"{message.author.display_name}: {message.content}"
            )

            # Include current message images in prompt
            if current_attachments:
                image_context = "\n".join(
                    f"[Attached image '{a['filename']}': {a['description']}]"
                    for a in current_attachments
                )
                user_prompt += f"\n{image_context}"

            last_exc: Exception | None = None
            for attempt in range(LLM_MAX_RETRIES):
                try:
                    result = await self.agent.run(user_prompt, deps=deps)
                    response = result.output
                    thinking = _extract_thinking(result)

                    # Retry once if model produced thinking but no response
                    if not response:
                        nudge = (
                            f"{user_prompt}\n\n"
                            "You produced reasoning but no visible response. "
                            "Please respond to the user directly."
                        )
                        result = await self.agent.run(nudge, deps=deps)
                        response = result.output
                        thinking = _extract_thinking(result)
                        if not response:
                            response = (
                                "Sorry, I'm having trouble formulating a response. "
                                "Please try again."
                            )

                    # Summarize long thinking
                    if thinking:
                        thinking = await _summarize_thinking(thinking)

                    return response, thinking
                except Exception as exc:
                    last_exc = exc
                    if attempt < LLM_MAX_RETRIES - 1:
                        delay = LLM_RETRY_BASE_DELAY * (2**attempt)
                        logger.warning(
                            "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                            attempt + 1,
                            LLM_MAX_RETRIES,
                            delay,
                            exc,
                        )
                        await asyncio.sleep(delay)
            raise last_exc


def create_bot() -> ChatBot:
    """Factory function for the Discord bot."""
    return ChatBot()
