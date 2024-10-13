from services.discord_bots.hello.client import HelloBot
from services.discord_bots.shared.discord_client import create_discord_intents
from services.discord_bots.shared.discord_bot_health_checks import (
    default_discord_bot_health_checks,
)


def run_hello_bot() -> None:
    client = HelloBot(intents=create_discord_intents())
    client.run_health_check_service(default_discord_bot_health_checks(client))
    client.run(
        "MTI5MDY4MTY4Mjc2NDEwMzc5MQ.Gy4r8j.tQPe8KVbiix5ldasAaYMXhaLw6NmuhysBLk9ls"
    )
    client.stop_health_check_service()


if __name__ == "__main__":
    run_hello_bot()
