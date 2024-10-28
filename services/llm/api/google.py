"""Gemini API Route"""

import asyncio
import logging
from typing import Literal

import aiohttp
import google.generativeai as genai
import structlog
from google.generativeai.types import helper_types
from google.generativeai.types.safety_types import HarmBlockThreshold, HarmCategory
from pydantic_settings import BaseSettings, SettingsConfigDict
import opentelemetry.trace as trace
from api.types import InputMediaContent, LLMRequest, LLMResponse, LLMResponseMetadata

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)


class GeminiConfig(BaseSettings):
    API_KEY: str
    MODEL_NAME: str = "gemini-1.5-flash"

    model_config = SettingsConfigDict(
        env_prefix="GEMINI_",
    )


SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}
GEMINI_CONFIG = GeminiConfig()
genai.configure(api_key=GEMINI_CONFIG.API_KEY)


AcceptedMimeTypes = Literal[
    "image/png",
    "image/jpeg",
    "image/webp",
    "video/x-flv",
    "video/quicktime",
    "video/mpeg",
    "video/mpegps",
    "video/mpg",
    "video/mp4",
    "video/webm",
    "video/wmv",
    "video/3gpp",
    "audio/aac",
    "audio/flac",
    "audio/mp3",
    "audio/m4a",
    "audio/mpeg",
    "audio/mpga",
    "audio/mp4",
    "audio/ogg",
    "audio/opus",
    "audio/pcm",
    "audio/wav",
    "audio/webm",
    "application/pdf",
    "text/plain",
]


class GeminiInputMediaContent(InputMediaContent):
    """Input media content for Gemini"""

    mime_type: AcceptedMimeTypes


async def gemini_inference(request: LLMRequest) -> LLMResponse:
    """Infer response using gemini and persona"""
    tracer = trace.get_tracer(__name__)
    logger.info(
        "Starting inference.",
        content=[
            (f"file: {item.url}" if isinstance(item, InputMediaContent) else item[:50])
            for item in request.content
        ],
    )
    model = genai.GenerativeModel(
        GEMINI_CONFIG.MODEL_NAME,
        system_instruction=request.prompt,
    )
    async with aiohttp.ClientSession() as session:
        retrieve_file_tasks = [
            item.retrieve_data(session)
            for item in request.content
            if isinstance(item, InputMediaContent)
        ]
        attachments = await asyncio.gather(*retrieve_file_tasks)
    formatted_content = [
        *attachments,
        *[item for item in request.content if not isinstance(item, InputMediaContent)],
    ]

    model_metadata = {
        "gen_ai.request.model": GEMINI_CONFIG.MODEL_NAME,
        "gen_ai.request.max_tokens": 8192,
        "gen_ai.request.temperature": 0,
        "gen_ai.system": "google",
        "gen_ai.operation.name": "text-completion",
    }
    with tracer.start_as_current_span(
        "llm.infer.request",
        attributes=model_metadata,
    ), structlog.contextvars.bound_contextvars(
        **model_metadata,
    ):

        response = await model.generate_content_async(
            formatted_content,
            request_options=helper_types.RequestOptions(timeout=300),
            safety_settings=SAFETY_SETTINGS,
        )
        metadata = LLMResponseMetadata(
            total_token_count=response.usage_metadata.total_token_count,
            cached_content_token_count=response.usage_metadata.cached_content_token_count,
            candidates_token_count=response.usage_metadata.candidates_token_count,
            prompt_token_count=response.usage_metadata.prompt_token_count,
        )

    logger.info(
        "Completed inference.",
        content=[
            (f"file: {item.url}" if isinstance(item, InputMediaContent) else item[:50])
            for item in request.content
        ],
        response=response.text[:50],
        metadata=metadata.model_dump(),
    )
    return LLMResponse(
        text=response.text,
        metadata=metadata,
    )
