from unidecode import unidecode
import discord
from services.discord_bots.shared.discord_client import DiscordBot


class HelloBot(DiscordBot):
    greetings: list[str]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.greetings = _create_greetings_list()

    async def on_message(self, message: discord.Message) -> None:
        """Say hello back whenever someone else says hello?"""
        if message.author.id == self.user.id or message.author.bot:
            return
        if message.channel.name not in ["bot-test", "general"]:
            return

        message_content = _strip_all_non_alphabet_characters(message.content)
        message_content = _normalize_foreign_characters(message_content)
        for greeting in self.greetings:
            if greeting in message_content.lower():
                await message.channel.send("Hello!")
                return


def _strip_all_non_alphabet_characters(message: str) -> str:
    """Remove non alphabet characters"""
    return "".join([character for character in message if character.isalpha()])


def _normalize_foreign_characters(message: str) -> str:
    """Normalize foreign characters"""
    return unidecode(message)


def _create_greetings_list() -> list[str]:
    greetings = [
        "Hello",  # English
        "Nǐ hǎo",  # Mandarin Chinese
        "Hola",  # Spanish
        "Namaste",  # Hindi
        "Marhaban",  # Arabic
        "Bonjour",  # French
        "Zdravstvuyte",  # Russian
        "Olá",  # Portuguese
        "Konnichiwa",  # Japanese
        "Hallo",  # German
        "Annyeonghaseyo",  # Korean
        "Ciao",  # Italian
        "Yassou",  # Greek
        "Merhaba",  # Turkish
        "Cześć",  # Polish
        "Hej",  # Swedish
        "Xin chào",  # Vietnamese
        "Sawasdee",  # Thai
        "Halo",  # Indonesian
        "Shalom",  # Hebrew
        "Jambo",  # Swahili
        "Ahoj",  # Czech
        "Szia",  # Hungarian
        "Salut",  # Romanian
        "Kumusta",  # Tagalog
        "Nomoshkar",  # Bengali
    ]
    return [
        _strip_all_non_alphabet_characters(
            _normalize_foreign_characters(greeting)
        ).lower()
        for greeting in greetings
    ]
