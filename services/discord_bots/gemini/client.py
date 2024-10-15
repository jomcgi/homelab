import io
import random
import discord
from services.discord_bots.gemini.personas import GeminiPersona
from services.discord_bots.gemini.prompts import ERROR_PROMPT
from services.discord_bots.shared.discord_client import (
    DiscordBot,
    LogLevel,
    chunk_string,
)
import google.generativeai as genai
from PIL import Image
from google.generativeai.types import helper_types
from google.generativeai.types.safety_types import HarmBlockThreshold, HarmCategory
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


def _get_persona(message: str) -> GeminiPersona | None:
    """Get the persona name from the message"""
    for persona in GeminiPersona:
        if message.content.lower().startswith(f"!{persona.name.lower()}"):
            return persona
    if message.content.lower().startswith("!gemini"):
        return random.choice(list(GeminiPersona))


def _format_gemini_response(response: str) -> str:
    """Format the response for discord"""
    formatted = response.replace("\n ", "\n")
    formatted = response.replace("\n", "\n\n").replace("\n\n\n", "\n\n")
    return formatted


class GeminiBot(DiscordBot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def _transcribe_voice_message(
        self, message: discord.Message, attachment: discord.Attachment
    ) -> str:
        """Transcribe the voice message"""
        if attachment.content_type not in [
            "audio/wav",
            "audio/mp3",
            "audio/aiff",
            "audio/aac",
            "audio/ogg",
            "audio/flac",
        ]:
            await self.log(
                f"Unsupported audio format: {attachment.content_type}", LogLevel.ERROR
            )

        response = await model.generate_content_async(
            [
                "Transcribe voice message, use emojis to convey emotions.",
                {
                    "mime_type": attachment.content_type,
                    "data": await attachment.read(),
                },
            ],
            request_options=helper_types.RequestOptions(timeout=300),
        )
        transcription = f"""
Transcription:
```
{response.text}
```
"""
        await message.reply(transcription)

    async def on_message(self, message: discord.Message) -> None:

        if message.author.id == self.user.id or message.author.bot:
            return
        if message.channel.name not in ["bot-test", "general"]:
            return
        if len(message.attachments) > 0:
            for attachment in message.attachments:
                attach: discord.Attachment = attachment
                if attach.is_voice_message():
                    await self.log(
                        f"Voice message received from {message.author.display_name}",
                        LogLevel.INFO,
                    )
                    await self._transcribe_voice_message(message, attach)
        if message.content.lower().startswith("!help"):
            await self.log("Help command triggered", LogLevel.INFO)
            await message.channel.send(
                f"""
Commands:
```
!gemini: Randomly select a persona
```
Personas:
```
!{"\n!".join([persona.name.lower() for persona in GeminiPersona])}
```
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
        formatted_response = _format_gemini_response(gemini_response)
        await self.log("Gemini response:", LogLevel.INFO)
        await self.log(formatted_response, LogLevel.INFO)
        for chunk in chunk_string(formatted_response):
            await message.channel.send(chunk)

    async def _gemini_inference(
        self, message: str, attachments: list[discord.File], persona: GeminiPersona
    ) -> str:
        """Infer the response to the message"""
        content = [
            persona.value,
            f"Your Persona: {persona.name}\n\n{persona.value}",
            f"User message: {message}",
            "Response Format: Create a multi-line markdown formatted string.",
        ]
        if len(persona.value) < 5000:
            await self.log("Content sent to gemini:", LogLevel.INFO)
            for c in content:
                await self.log(c, LogLevel.INFO)
        else:
            await self.log("Content sent to gemini is too long to log", LogLevel.INFO)
        for attachment in attachments:
            if attachment.filename.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")
            ):
                image_bytes = attachment.fp.read()
                image = Image.open(io.BytesIO(image_bytes))
                content.append(image)
        response = await model.generate_content_async(
            content,
            request_options=helper_types.RequestOptions(timeout=300),
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            },
        )
        try:
            return response.text
        except ValueError as e:
            await self.log(f"Error generating response: {e}", LogLevel.ERROR)
            return await self._handle_gemini_error(message, persona.value, e)

    async def _handle_gemini_error(
        self,
        message: str,
        prompt: str,
        error: Exception,
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
