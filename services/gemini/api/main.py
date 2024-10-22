"""Gemini Discord bot API"""

import asyncio
import logging
from typing import Literal

import aiohttp
import google.generativeai as genai
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from google.generativeai.types import helper_types
from google.generativeai.types.safety_types import HarmBlockThreshold, HarmCategory
from pydantic import BaseModel

from instrumentation import _instrument
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

GEMINI_KEY = "AIzaSyAZ7vtxrojMJSrXBs7oKJe4ehTEON1rVcQ"

SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel(
    "gemini-1.5-flash",
)


class HealthResponse(BaseModel):
    """Response class for health check"""

    OK: bool = True
    utils_health: dict[str, bool] | None = None


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


async def get_content_from_url(session: aiohttp.ClientSession, url: str) -> bytes:
    async with session.get(url) as resp:
        if resp.status == 200:
            return await resp.read()
        elif resp.status == 404:
            raise FileNotFoundError("asset not found")
        elif resp.status == 403:
            raise PermissionError("access denied")
        else:
            raise HTTPException(resp, "failed to get asset")

    raise RuntimeError("Unreachable")


class MediaContent(BaseModel):
    """Accepted media content types"""

    data: bytes
    mime_type: AcceptedMimeTypes


class InputMediaContent(BaseModel):
    """Input media content"""

    url: str
    mime_type: AcceptedMimeTypes

    async def retrieve_data(
        self, session: aiohttp.ClientSession
    ) -> dict[str, str | bytes]:
        return MediaContent(
            data=await get_content_from_url(session, self.url),
            mime_type=self.mime_type,
        ).model_dump()


app = FastAPI(
    on_startup=[_instrument],
)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")


@app.get("/health", status_code=200, response_model=HealthResponse)
async def get_health():
    """Health check route"""
    logger.debug("Successful Health Check")
    return HealthResponse()


class LLMResponseMetadata(BaseModel):
    """Response metadata for LLM inference"""

    total_token_count: int
    cached_content_token_count: int
    candidates_token_count: int
    prompt_token_count: int


class LLMResponse(BaseModel):
    """Response class for LLM inference"""

    text: str
    metadata: LLMResponseMetadata


@app.post("/infer")
async def infer(content: list[InputMediaContent | str]) -> LLMResponse:
    """Infer response using gemini and persona"""
    logger.info(
        "Starting inference.",
        content=[
            (f"file: {item.url}" if isinstance(item, InputMediaContent) else item[:50])
            for item in content
        ],
    )
    async with aiohttp.ClientSession() as session:
        retrieve_file_tasks = [
            item.retrieve_data(session)
            for item in content
            if isinstance(item, InputMediaContent)
        ]
        attachments = await asyncio.gather(*retrieve_file_tasks)
    formatted_content = [
        *attachments,
        *[item for item in content if not isinstance(item, InputMediaContent)],
    ]

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
            for item in content
        ],
        response=response.text[:50],
        metadata=metadata.model_dump(),
    )
    return LLMResponse(
        text=response.text,
        metadata=metadata,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9090)
