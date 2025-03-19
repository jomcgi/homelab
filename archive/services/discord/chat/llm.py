from typing import Literal
from pydantic import BaseModel
import aiohttp
import structlog
from opentelemetry.instrumentation.aiohttp_client import create_trace_config
from services.discord.chat.instrumentation import _add_to_current_span
import opentelemetry.trace as trace
from pydantic_core import ValidationError

logger = structlog.get_logger(__name__)

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


class MediaContent(BaseModel):
    """Accepted media content types"""

    url: str
    mime_type: AcceptedMimeTypes


class LLMResponseMetadata(BaseModel):
    """Response metadata for LLM inference"""

    total_token_count: int
    cached_content_token_count: int
    candidates_token_count: int
    prompt_token_count: int

    def __post_init__(self):
        _add_to_current_span(
            {
                "gen_ai.usage.input_tokens": self.prompt_token_count,
                "gen_ai.usage.output_tokens": self.candidates_token_count,
                "gen_ai.usage.total_tokens": self.total_token_count,
            }
        )


class LLMResponse(BaseModel):
    """Response class for LLM inference"""

    text: str
    metadata: LLMResponseMetadata


async def infer(
    prompt: str,
    content: list[str | MediaContent],
    model: Literal["anthropic", "gemini"],
) -> LLMResponse:
    """Infer the response to the message"""
    model_url = f"http://llm.llm.svc.cluster.local:80/infer/{model}"
    data = [
        media.model_dump() if isinstance(media, MediaContent) else media
        for media in content
    ]
    payload = {
        "prompt": prompt,
        "content": data,
    }

    async with aiohttp.ClientSession(
        trace_configs=[
            create_trace_config(
                tracer_provider=trace.get_tracer_provider(),
            )
        ]
    ) as session:
        async with session.post(model_url, json=payload) as response:
            result = await response.json()
    try:
        return LLMResponse.model_validate(result)
    except ValidationError as e:
        logger.error(
            "Failed to validate response",
            response=response,
            result=result,
            exc_info=e,
        )
        response.raise_for_status()
        raise
