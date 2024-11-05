import random
import discord
from typing import get_args
from services.discord.chat.commands.types import COMMAND_HANDLER
from services.discord.chat.format_text import _format_text_for_discord
from services.discord.chat.instrumentation import (
    _add_to_current_span,
    _reply_with_trace_info,
)
import services.discord.chat.llm as llm
from services.discord.chat.personas import ChatPersona
import structlog
import re

logger = structlog.get_logger(__name__)


def _get_valid_attachments(
    attachments: list[discord.Attachment],
) -> list[llm.MediaContent]:
    if not attachments:
        return []
    logger.info(
        "Processing attachments",
        attachments=[attachment.filename for attachment in attachments],
    )
    attachments = [
        llm.MediaContent(url=attachment.url, mime_type=attachment.content_type)
        for attachment in attachments
        if attachment.content_type in get_args(llm.AcceptedMimeTypes)
    ]

    logger.info(
        "Finished processing attachments",
        attachments=[attachment.url for attachment in attachments],
    )
    return attachments


async def _send_chat_response(
    message: discord.Message, response: llm.LLMResponse
) -> None:
    formatted_response = _format_text_for_discord(response.text)
    logger.info(
        "Responding with chat messages",
        response=formatted_response,
    )
    if len(formatted_response) > 1:
        for chunk in formatted_response[:-1]:
            await message.reply(
                chunk,
                mention_author=True,
            )
        await _reply_with_trace_info(message, formatted_response[-1])
    else:
        await _reply_with_trace_info(message, formatted_response[0])
    logger.info(
        "Chat messages sent",
    )


async def _generate_response(
    message: discord.Message,
    persona: ChatPersona,
):
    content: list[llm.MediaContent | str] = [
        *_get_valid_attachments(message.attachments),
        f"User Message: {re.sub(f"(?i)^!{persona.name}", "", message.content)}",
    ]
    response = await llm.infer(persona.value, content, "gemini")
    await _send_chat_response(message, response)


async def _chat_command(message: discord.Message) -> None:
    """Chat with a random persona"""

    logger.info(
        "Processing !chat command",
        content=message.content,
    )
    persona = random.choice(list(ChatPersona))
    _add_to_current_span(
        {
            "discord.bot.command": "chat",
            "discord.bot.persona": persona.name,
        }
    )
    await _generate_response(message, persona=persona)
    logger.info(
        "Finished processing !chat command",
        persona=persona.name,
    )


def _create_persona_func(persona: ChatPersona) -> COMMAND_HANDLER:
    async def _persona_command(message: discord.Message) -> None:
        """Chat with AI as a specific persona"""
        _add_to_current_span(
            {
                "discord.bot.command": persona.name,
                "discord.bot.persona": persona.name,
            }
        )
        with structlog.contextvars.bound_contextvars(
            persona=persona.name,
        ):
            logger.info(
                "Processing persona command",
                content=message.content,
                persona=persona.name,
            )
            await _generate_response(message, persona=persona)
            logger.info(
                "Finished processing persona command",
                persona=persona.name,
            )

    return _persona_command
