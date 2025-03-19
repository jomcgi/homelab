import discord
import structlog
from services.discord.chat.format_text import _format_text_for_discord
from services.discord.chat.instrumentation import (
    _add_to_current_span,
    _reply_with_trace_info,
)
import services.discord.chat.llm as llm

logger = structlog.get_logger(__name__)


def _retrieve_voice_message(message: discord.Message) -> discord.Attachment | None:
    for attachment in message.attachments:
        attach: discord.Attachment = attachment
        if attach.is_voice_message():
            return attach
    return None


async def _transcribe_voice_message(
    voice_attachment: discord.Attachment, message: discord.Message
) -> str | None:
    try:
        _add_to_current_span(
            {
                "discord.bot.attachment.filename": voice_attachment.filename,
                "discord.bot.attachment.url": voice_attachment.url,
                "discord.bot.attachment.content_type": voice_attachment.content_type,
            }
        )
        logger.info(
            "Transcribing voice message",
            content=[voice_attachment.filename],
        )
        prompt = "This is a voice message from a group chat. Transcribe the message as accurately as possible. Use emojis to convey the speakers tone."
        content = [
            llm.MediaContent(
                url=voice_attachment.url, mime_type=voice_attachment.content_type
            ),
        ]
        transcription = await llm.infer(prompt, content, "gemini")
        logger.info(
            "Voice message transcribed",
            content=[voice_attachment.filename],
            response=transcription,
        )
        formatted_transcription = _format_text_for_discord(transcription.text)
        logger.info(
            "Responding with transcribed message.",
        )
        if len(formatted_transcription) > 1:
            for chunk in formatted_transcription[:-1]:
                await message.reply(chunk)
            await _reply_with_trace_info(message, formatted_transcription[-1])
        else:
            await _reply_with_trace_info(message, formatted_transcription[0])
        logger.info(
            "Transcribed message sent.",
        )
        return transcription.text
    except Exception as e:
        logger.exception("Error transcribing voice message", exc_info=e)
        return None
