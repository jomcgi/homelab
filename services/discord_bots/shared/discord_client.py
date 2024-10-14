from enum import Enum
from typing import Any
import discord
import logging

from services.discord_bots.shared.health_check import (
    HealthServer,
    run_http_service,
    stop_server,
)
from services.discord_bots.shared.health_protocol import Healthable

logging.basicConfig(level=logging.INFO)


class LogLevel(Enum):
    ERROR = logging.ERROR
    INFO = logging.INFO


class DiscordBot(discord.Client):
    error_count: int = 0
    health_server: HealthServer | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)

    async def log(self, message: str, level: LogLevel) -> None:
        self.logger.log(level.value, message)
        channel = self.get_channel(1295313022432051220)
        if channel is not None:
            for chunk in chunk_string(message):
                await channel.send(f"```{chunk}```")

    async def on_error(self, event_method: str, /, *args: Any, **kwargs: Any) -> None:
        self.error_count += 1
        return await super().on_error(event_method, *args, **kwargs)

    def run_health_check_service(self, health_checks: list[Healthable]) -> None:
        health_server = run_http_service(health_checks)
        self.health_server = health_server

    def stop_health_check_service(self) -> None:
        stop_server(self.health_server)
        self.health_server = None


def create_discord_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True
    return intents


def chunk_string(text: str, max_chunk_size=1990) -> list[str]:
    words = text.split()
    chunks = []
    current_chunk = []

    for word in words:
        if len(" ".join(current_chunk)) + len(word) + 1 <= max_chunk_size:
            current_chunk.append(word)
        else:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]

    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks
