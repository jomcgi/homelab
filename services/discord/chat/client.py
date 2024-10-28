import discord
import structlog
from services.discord.chat.commands.handler import (
    extract_command,
)
from services.discord.chat.instrumentation import _add_to_current_span
from services.discord.chat.micro import _detect_microaggression, _handle_microaggression
from services.discord.chat.voice_message import (
    _retrieve_voice_message,
    _transcribe_voice_message,
)
from services.discord.shared.discord_client import (
    DiscordBot,
)
from opentelemetry.context.context import Context
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


async def _send_error_response(message: discord.Message) -> None:
    span = trace.get_current_span()
    span_ctx = span.get_span_context()
    trace_id = trace.format_trace_id(span_ctx.trace_id)
    start = int(message.created_at.timestamp() * 1000) - 300000
    end = int(discord.utils.utcnow().timestamp() * 1000) + 300000
    dashboard_url = "https://grafana.jomcgi.dev/d/ce1n5j1xiggzkf/trace-view?orgId=1"
    error_url = f"{dashboard_url}&var-trace_id={trace_id}&from={start}&to={end}"
    await message.reply(
        "Error occured generating response.",
        embed=discord.Embed(title="View error details", url=error_url),
    )


class ChatBot(DiscordBot):
    """Discord Chat Bot"""

    async def on_message(self, message: discord.Message) -> None:
        tracer = trace.get_tracer(__name__)
        with _message_contextvars(message):
            with tracer.start_as_current_span(
                "discord.message",
                attributes={
                    "message.id": message.id,
                    "message.author.id": message.author.id,
                    "message.author.name": message.author.name,
                    "message.channel.id": message.channel.id,
                    "message.channel.name": message.channel.name,
                    "message.guild.id": message.guild.id,
                    "message.guild.name": message.guild.name,
                    SpanAttributes.HTTP_STATUS_CODE: 200,
                },
            ):
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
                            context=Context(),
                        ):
                            if transcription := await _transcribe_voice_message(
                                voice_attachment, message
                            ):
                                message.content = transcription + message.content

                    if command := extract_command(message.content):
                        with tracer.start_as_current_span(
                            "discord.bot.command",
                        ):
                            await command(message)
                            return
                    if message.content:
                        _add_to_current_span(
                            {
                                "discord.bot.command": "detect_microaggression",
                            }
                        )
                        with tracer.start_as_current_span(
                            "discord.bot.microaggression",
                        ):
                            if micro_agression := await _detect_microaggression(
                                message.content
                            ):
                                await _handle_microaggression(message, micro_agression)
                            else:
                                _add_to_current_span(
                                    {"discord.bot.microaggression.detected": "false"}
                                )

                except Exception as e:
                    logger.exception("Error processing message", exc_info=e)
                    await _send_error_response(message)
