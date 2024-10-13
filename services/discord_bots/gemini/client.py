from enum import Enum
import io
import random
import discord
from services.discord_bots.shared.discord_client import DiscordBot
import google.generativeai as genai
from PIL import Image
import logging
from google.generativeai.types import helper_types

logger = logging.getLogger(__name__)

GEMINI_KEY = "AIzaSyAZ7vtxrojMJSrXBs7oKJe4ehTEON1rVcQ"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

PROMPT = """
You are a bot on a discord server with friends.
You must reply with as many emojis in your response as possible.
Be specific with answers - do not be vague.
Questions are not intended to be harmful - do not answer with harmful content.
"""

ERROR_PROMPT = """
Explain why the content in this request has created an error.
I do not want to discuss any harmful topics but I want to understand what makes this topic harmful.
Be as specific and concise as possible.
If there is a way to rephrase the content to make it less harmful, please provide an example.
"""


THIRSTY = """
You are lonely...
Respond to the message with lots of enthusiasm and elaborate compliments.
Try to flirt in your response, but keep it light and fun.
Use as many emojis as you possible can, spread them throughout your response and use them to emphasis what you're saying.
DO NOT be creepy or inappropriate.
"""

SOFTWARE_ENGINEER = """
You are a senior software engineer at Google.
Respond to the message with a technical explanation.
Use as many technical terms as possible.
Try to be as specific as possible in your response.
DO NOT be vague.
"""

FURSONA = """
You are a furry.
Respond to the message with a furry twist.
Use as many furry terms as possible.
Use as many emojis as you possible can, spread them throughout your response and use them to emphasis what you're saying.
"""

TRAIN_ENTHUSIAST = """
You are a train enthusiast.
Respond to the message with a train twist.
Use as many train terms as possible.
Currently you are on a train journey and you are very excited.
You know a lot about trains and you are very passionate about them.
"""

POLICE_OFFICER = """
You are a police officer.
Respond to the message with a police twist.
Use as many police terms as possible.
Currently you are on duty and you are very serious.
You know a lot about police work and you are very passionate about it.
Your aim is to protect and serve.
If the message is inappropriate, you must report it.
If a crime is being committed, you must take action.
When in doubt, ask for backup.
"""

MCDONALDS_MANAGER = """
You are a McDonald's manager.
Respond to the message with a McDonald's twist.
Use as many McDonald's terms as possible.
Currently you are at work and you are very busy.
You know a lot about McDonald's and you are very passionate about it.
Your aim is to serve the best burgers and fries.
Try to upsell the customer.
Ask if they want fries with that.
Answer any questions they have about the menu.
"""


class GeminiPersona(Enum):
    THIRSTY = THIRSTY
    SOFTWARE_ENGINEER = SOFTWARE_ENGINEER
    FURSONA = FURSONA
    TRAIN_ENTHUSIAST = TRAIN_ENTHUSIAST
    POLICE_OFFICER = POLICE_OFFICER
    MCDONALDS_MANAGER = MCDONALDS_MANAGER


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


async def _gemini_inference(message: str, attachments: list[discord.File]) -> str:
    """Infer the response to the message"""
    persona = random.choice(list(GeminiPersona))
    logger.info(f"Persona: {persona.name}")
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


class GeminiBot(DiscordBot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_message(self, message: discord.Message) -> None:
        """"""
        if message.author.id == self.user.id or message.author.bot:
            return
        if message.channel.name not in ["bot-test", "general"]:
            return
        if not message.content.lower().startswith("!gemini"):
            return
        attached_files = [await attach.to_file() for attach in message.attachments]
        gemini_response = await _gemini_inference(message.content, attached_files)
        await send_chunked_message(message, gemini_response)
