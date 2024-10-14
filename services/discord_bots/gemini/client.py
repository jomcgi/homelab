import io
import random
import discord
from services.discord_bots.gemini.personas import GeminiPersona
from services.discord_bots.gemini.prompts import ERROR_PROMPT, PROMPT
from services.discord_bots.shared.discord_client import (
    DiscordBot,
    LogLevel,
    chunk_string,
)
import google.generativeai as genai
from PIL import Image
import logging
from google.generativeai.types import helper_types
import json

GEMINI_KEY = "AIzaSyAZ7vtxrojMJSrXBs7oKJe4ehTEON1rVcQ"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


def _explain_error_prompt(message: str, error: str, prompt: str) -> str:
    error_prompt = f"""
    {ERROR_PROMPT}
    ORIGINAL PROMPT: {prompt}
    ORIGINAL MESSAGE: {message}
    ORIGINAL ERROR: {error}
    """
    return [
        error_prompt,
    ]


async def _handle_gemini_error(
    self, message: str, prompt: str, error: Exception, logger: logging.Logger
) -> str:
    try:
        response = await model.generate_content_async(
            _explain_error_prompt(message, str(error), prompt),
            request_options=helper_types.RequestOptions(timeout=300),
        )
        text = response.text
    except ValueError as e:
        await self.log(f"Error explaining error: {e}", LogLevel.ERROR)
        safety_ratings = vars(error)
        return f"Error generating response:\n\n```{json.dumps(safety_ratings, indent=2)}```"
    return f"Unable to generate response:\n\n{text}"


def _get_persona(message: str) -> GeminiPersona | None:
    """Get the persona name from the message"""
    for persona in GeminiPersona:
        if message.content.lower().startswith(f"!{persona.name.lower()}"):
            return persona
    if message.content.lower().startswith("!gemini"):
        return random.choice(list(GeminiPersona))


class GeminiBot(DiscordBot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_message(self, message: discord.Message) -> None:

        if message.author.id == self.user.id or message.author.bot:
            return
        if message.channel.name not in ["bot-test", "general"]:
            return
        if message.content.lower().startswith("!help"):
            await self.log("Help command triggered", LogLevel.INFO)
            await message.channel.send(
                f"""
I am Gemini, an AI assistant.
You can ask me questions or provide prompts, and I will respond with helpful information.
You can also specify a persona to guide my responses.
Here are the available personas:
{", ".join([persona.name.lower() for persona in GeminiPersona])}
                """
            )
        persona = _get_persona(message)
        if persona is None:
            return
        await self.log(
            f"Messaged received: {message.content} from {message.author.display_name}",
            LogLevel.INFO,
        )
        await self.log(f"Persona selected: {persona.name}", LogLevel.INFO)
        attached_files = [await attach.to_file() for attach in message.attachments]
        gemini_response = await self._gemini_inference(
            message.content, attached_files, persona
        )
        await self.log("Gemini response:", LogLevel.INFO)
        await self.log(gemini_response, LogLevel.INFO)
        for chunk in chunk_string(gemini_response):
            await message.channel.send(chunk)

    async def _gemini_inference(
        self, message: str, attachments: list[discord.File], persona: GeminiPersona
    ) -> str:
        """Infer the response to the message"""
        prompt = PROMPT + "\n\n" + persona.value
        content = [
            PROMPT,
            f"Your Persona: {persona.name}\n\n{persona.value}",
            f"User message: {message}",
        ]
        await self.log("Content sent to gemini:", LogLevel.INFO)
        for c in content:
            await self.log(c, LogLevel.INFO)
        for attachment in attachments:
            if attachment.filename.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")
            ):
                image_bytes = attachment.fp.read()
                image = Image.open(io.BytesIO(image_bytes))
                content.append(image)
        response = await model.generate_content_async(
            content, request_options=helper_types.RequestOptions(timeout=300)
        )
        try:
            return response.text
        except ValueError as e:
            await self.log(f"Error generating response: {e}", LogLevel.ERROR)
            return await _handle_gemini_error(message, prompt, e)
