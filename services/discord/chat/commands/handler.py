import re
import discord
import structlog

from services.discord.chat.commands.chat import _chat_command, _create_persona_func
from services.discord.chat.commands.types import COMMAND_HANDLER
from services.discord.chat.instrumentation import _add_to_current_span
from services.discord.chat.personas import ChatPersona


logger = structlog.get_logger(__name__)


async def _help_command(message: discord.Message) -> None:
    """Display help message"""
    _add_to_current_span(
        {
            "discord.bot.command": "help",
        }
    )
    await message.reply(
        HELP_MESSAGE,
        mention_author=True,
    )


STATIC_COMMAND_MAPPING: dict[str, COMMAND_HANDLER] = {
    "help": _help_command,
    "chat": _chat_command,
}

PERSONA_COMMAND_MAPPING: dict[str, COMMAND_HANDLER] = {
    persona.name.lower(): _create_persona_func(persona) for persona in ChatPersona
}


COMMAND_MAPPING: dict[str, COMMAND_HANDLER] = {
    **STATIC_COMMAND_MAPPING,
    **PERSONA_COMMAND_MAPPING,
}


HELP_MESSAGE = f"""
Commands:
```
{"\n".join([f"!{command}\t\t{func.__doc__}" for command, func in STATIC_COMMAND_MAPPING.items()])}
```
Personas:
```
!{"\n!".join(sorted([persona.name.lower() for persona in ChatPersona]))}
```
"""


def extract_command(message: str) -> COMMAND_HANDLER | None:
    logger.info("Extracting command", message=message)
    pattern = r"^!([\w]+)"
    match = re.match(pattern, message.lower())
    if not match:
        _add_to_current_span(
            {
                "discord.bot.command": "not_found",
            }
        )
        return
    potential_command = match.group(1)
    try:
        handler = COMMAND_MAPPING[potential_command]
        logger.info(
            "Command found", command=potential_command, handler=handler.__name__
        )
        _add_to_current_span(
            {
                "discord.bot.command": potential_command,
            }
        )
        return handler
    except KeyError:
        logger.info("Command not found", command=potential_command)
        _add_to_current_span(
            {
                "discord.bot.command": "not_found",
            }
        )
        return
