from typing import Any
import discord
import logging
from discord.ext.commands import Bot

from services.discord_bots.shared.health_check import (
    HealthServer,
    run_http_service,
    stop_server,
)
from services.discord_bots.shared.health_protocol import Healthable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DiscordBot(discord.Client):
    error_count: int = 0
    health_server: HealthServer | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_error(self, event_method: str, /, *args: Any, **kwargs: Any) -> None:
        self.error_count += 1
        return await super().on_error(event_method, *args, **kwargs)

    def run_health_check_service(self, health_checks: list[Healthable]) -> None:
        health_server = run_http_service(health_checks)
        self.health_server = health_server

    def stop_health_check_service(self) -> None:
        stop_server(self.health_server)
        self.health_server = None


class DiscordCommandBot(Bot):
    error_count: int = 0
    health_server: HealthServer | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
