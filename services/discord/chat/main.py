import structlog
from services.discord.chat.instrumentation import _instrument
from services.discord.chat.log_config import configure_structlog
from services.discord.chat.client import ChatBot
from services.discord.shared.discord_client import create_discord_intents
from services.discord.shared.discord_bot_health_checks import (
    default_discord_bot_health_checks,
)

configure_structlog()
logger = structlog.get_logger(__name__)


def run_chat_bot() -> None:
    _instrument()
    logger.info("Running Chat Bot")
    client = ChatBot(intents=create_discord_intents(), command_prefix="/")
    client.run_health_check_service(default_discord_bot_health_checks(client))
    logger.info("Starting Chat Bot")
    client.run(
        "MTI5NDc4ODc2OTY3MjU5MzUwMQ.GCxqyf.-Jr_EEAUVou_W9odu6PsMcoY33qmAiTnmNSKJQ"
    )
    client.stop_health_check_service()
    logger.info("Chat Bot & Health Check Service Stopped")


if __name__ == "__main__":
    run_chat_bot()
