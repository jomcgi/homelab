import io
import random
import discord
from services.discord_bots.gemini.personas import GeminiPersona
from services.discord_bots.gemini.prompts import ERROR_PROMPT, PROMPT
from services.discord_bots.shared.discord_client import DiscordBot
import google.generativeai as genai
from PIL import Image
import logging
from google.generativeai.types import helper_types

logger = logging.getLogger(__name__)

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


async def _gemini_inference(
    message: str, attachments: list[discord.File], persona: GeminiPersona
) -> str:
    """Infer the response to the message"""
    prompt = PROMPT + "\n\n" + persona.value
    content = [prompt, message]
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
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        response = await model.generate_content_async(
            _explain_error_prompt(message, str(e), prompt),
            request_options=helper_types.RequestOptions(timeout=300),
        )
        return response.text


async def send_chunked_message(message, text, max_chunk_size=2000):
    words = text.split()
    chunks = []
    current_chunk = []

    for word in words:
        if len(" ".join(current_chunk)) + len(word) + 1 <= max_chunk_size:
            current_chunk.append(word)
        else:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    for chunk in chunks:
        await message.channel.send(chunk)


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
        """"""
        if message.author.id == self.user.id or message.author.bot:
            return
        if message.channel.name not in ["bot-test", "general"]:
            return
        if message.content.lower().startswith("!help"):
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
        attached_files = [await attach.to_file() for attach in message.attachments]
        gemini_response = await _gemini_inference(
            message.content, attached_files, persona
        )
        await send_chunked_message(message, gemini_response)
