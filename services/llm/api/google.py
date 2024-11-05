"""Google API Route"""

import logging

import structlog
from api.types import LLMRequest, LLMResponse, LLMResponseMetadata
from api.search import get_search_context
from api.gemini import gemini_inference

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)


async def google_inference(request: LLMRequest) -> LLMResponse:

    search_context = await get_search_context(content=request.content)
    request.content.append(f"Context from Google Search: {search_context.text}")

    response = await gemini_inference(
        content=request.content,
        prompt=request.prompt,
    )

    return LLMResponse(
        text=response.text,
        metadata=LLMResponseMetadata(
            total_token_count=search_context.metadata.total_token_count
            + response.metadata.total_token_count,
            cached_content_token_count=search_context.metadata.cached_content_token_count
            + response.metadata.cached_content_token_count,
            candidates_token_count=search_context.metadata.candidates_token_count
            + response.metadata.candidates_token_count,
            prompt_token_count=search_context.metadata.prompt_token_count
            + response.metadata.prompt_token_count,
        ),
    )
