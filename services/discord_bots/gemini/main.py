from services.discord_bots.gemini.client import GeminiBot
from services.discord_bots.shared.discord_client import create_discord_intents
from services.discord_bots.shared.discord_bot_health_checks import (
    default_discord_bot_health_checks,
)


def run_gemini_bot() -> None:
    client = GeminiBot(intents=create_discord_intents(), command_prefix="/")
    client.run_health_check_service(default_discord_bot_health_checks(client))
    client.run(
        "MTI5NDc4ODc2OTY3MjU5MzUwMQ.GCxqyf.-Jr_EEAUVou_W9odu6PsMcoY33qmAiTnmNSKJQ"
    )
    client.stop_health_check_service()


if __name__ == "__main__":
    run_gemini_bot()
