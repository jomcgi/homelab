from services.discord_bots.shared.discord_client import (
    create_discord_intents,
    DiscordBot,
)


def run_test_bot() -> None:
    intents = create_discord_intents()
    client = DiscordBot(intents=intents)
    client.run(
        "MTI5MDY4MTY4Mjc2NDEwMzc5MQ.Gy4r8j.tQPe8KVbiix5ldasAaYMXhaLw6NmuhysBLk9ls"
    )
    channel = client.get_channel(1290714932157091850)
    channel.send("Hello, world!")


run_test_bot()
