from typing import Callable, Coroutine
from services.discord.chat.llm import MediaContent
import discord


COMMAND_HANDLER = Callable[
    [discord.Message, list[MediaContent]], Coroutine[None, None, None]
]
