from services.discord.shared.health_protocol import Healthable
from services.discord.shared.discord_client import DiscordBot


class NotRateLimited(Healthable):

    def __init__(self, client: DiscordBot):
        self.client = client

    def is_healthy(self) -> bool:
        return not self.client.is_ws_ratelimited()


class SocketOpen(Healthable):

    def __init__(self, client: DiscordBot):
        self.client = client

    def is_healthy(self) -> bool:
        return not self.client.is_closed()


class CacheReady(Healthable):

    def __init__(self, client: DiscordBot):
        self.client = client

    def is_healthy(self) -> bool:
        return self.client.is_ready()


class NoAppErrors(Healthable):

    def __init__(self, client: DiscordBot):
        self.client = client

    def is_healthy(self) -> bool:
        if self.client.error_count > 0:
            self.client.error_count = 0
            return False
        return True


def default_discord_bot_health_checks(client: DiscordBot) -> list[Healthable]:
    return [
        NotRateLimited(client),
        SocketOpen(client),
        CacheReady(client),
        NoAppErrors(client),
    ]
