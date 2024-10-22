import discord
import structlog
from services.discord.chat.commands.handler import (
    extract_command,
)
from services.discord.chat.instrumentation import _add_to_current_span, _message_span
from services.discord.chat.voice_message import (
    _retrieve_voice_message,
    _transcribe_voice_message,
)
from services.discord.shared.discord_client import (
    DiscordBot,
)
from opentelemetry.semconv.trace import SpanAttributes
import opentelemetry.trace as trace

logger = structlog.get_logger(__name__)


ALLOWED_CHANNELS = ["bot-test", "general", "chickenfriedrice"]


def _message_should_be_ignored(message: discord.Message) -> bool:
    if message.author.bot:
        return True
    if message.channel.name not in ALLOWED_CHANNELS:
        return True
    return False


def _message_contextvars(
    message: discord.Message,
) -> structlog.contextvars.bound_contextvars:
    return structlog.contextvars.bound_contextvars(
        message_id=message.id,
        author_id=message.author.id,
        author_name=message.author.name,
        channel_id=message.channel.id,
        channel_name=message.channel.name,
        server_id=message.guild.id,
        server_name=message.guild.name,
    )


# def _thread_conversation(discord_message: discord.Message) -> bool:
#     if discord_message.


class ChatBot(DiscordBot):
    """Discord Chat Bot"""

    async def on_message(self, message: discord.Message) -> None:
        with _message_contextvars(message), _message_span(message) as parent_span:
            try:
                if _message_should_be_ignored(message):
                    _add_to_current_span({"discord.bot.message.ignored": "true"})
                    return
                _add_to_current_span({"discord.bot.message.ignored": "false"})
                tracer = trace.get_tracer(__name__)
                if voice_attachment := _retrieve_voice_message(message):
                    _add_to_current_span(
                        {
                            "discord.bot.command": "transcribe_voice_message",
                        }
                    )
                    with tracer.start_as_current_span(
                        "discord.bot.transcribe_voice_message",
                        context=trace.set_span_in_context(parent_span),
                    ):
                        await _transcribe_voice_message(voice_attachment, message)
                if command := extract_command(message.content):
                    with tracer.start_as_current_span(
                        "discord.bot.command",
                        context=trace.set_span_in_context(parent_span),
                    ):
                        await command(message)
                        return
            except Exception as e:
                logger.exception("Error processing message", exc_info=e)
