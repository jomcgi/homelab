import discord
import structlog
from services.discord.chat.format_text import _format_text_for_discord
from services.discord.chat.instrumentation import _add_to_current_span
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
) -> None:
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
    content = [
        "This is a voice message from a group chat. Transcribe the message as accurately as possible. Use emojis to convey the speakers tone.",
        llm.MediaContent(
            url=voice_attachment.url, mime_type=voice_attachment.content_type
        ),
    ]
    transcription = await llm.infer(content)
    logger.info(
        "Voice message transcribed",
        content=[voice_attachment.filename],
        response=transcription,
    )
    formatted_transcription = _format_text_for_discord(transcription.text)
    logger.info(
        "Responding with transcribed message.",
    )
    for chunk in formatted_transcription:
        await message.reply(chunk)
    logger.info(
        "Transcribed message sent.",
    )
