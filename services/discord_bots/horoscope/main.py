from services.discord_bots.horoscope.client import HoroscopeBot
from services.discord_bots.shared.discord_client import create_discord_intents
from services.discord_bots.shared.discord_bot_health_checks import (
    default_discord_bot_health_checks,
)


def run_horoscope_bot() -> None:
    client = HoroscopeBot(intents=create_discord_intents())
    client.run_health_check_service(default_discord_bot_health_checks(client))
    client.run(
        "MTI5NDc1MjA2MDEzODMyODExNg.GK2Zgd.WRiZ4h7k_knPOenlDZ5aS40_3pX_LDiiu3GETw"
    )
    client.stop_health_check_service()


if __name__ == "__main__":
    run_horoscope_bot()
