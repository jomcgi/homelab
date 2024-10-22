from typing import Callable, Coroutine

import discord


COMMAND_HANDLER = Callable[[discord.Message], Coroutine[None, None, None]]
