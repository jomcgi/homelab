import json
import logging

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from api.types import LLMRequest, LLMResponse, LLMResponseMetadata
from anthropic import AsyncAnthropic
from anthropic.types import Message
import opentelemetry.trace as trace


logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)


class AnthropicConfig(BaseSettings):
    API_KEY: str
    MODEL_NAME: str = "claude-3-5-sonnet-20240620"

    model_config = SettingsConfigDict(
        env_prefix="ANTHROPIC_",
    )


ANTHROPIC_CONFIG = AnthropicConfig()

client = AsyncAnthropic(
    api_key=ANTHROPIC_CONFIG.API_KEY,
)


async def get_inference_response(
    request: LLMRequest, content: list[dict[str, str]]
) -> LLMResponse:
    tracer = trace.get_tracer(__name__)
    model_metadata = {
        "gen_ai.request.model": ANTHROPIC_CONFIG.MODEL_NAME,
        "gen_ai.request.max_tokens": 2000,
        "gen_ai.request.temperature": 0,
        "gen_ai.system": "anthropic",
        "gen_ai.operation.name": "text-completion",
    }
    with tracer.start_as_current_span(
        "llm.infer.request",
        attributes=model_metadata,
    ), structlog.contextvars.bound_contextvars(
        **model_metadata,
    ):
        response: Message = await client.messages.create(
            system=request.prompt,
            messages=content + [{"role": "assistant", "content": "{"}],
            model=ANTHROPIC_CONFIG.MODEL_NAME,
            max_tokens=4096,
            temperature=0,
            stop_sequences=["}"],
        )
        metadata = LLMResponseMetadata(
            total_token_count=response.usage.input_tokens
            + response.usage.output_tokens,
            cached_content_token_count=0,
            candidates_token_count=response.usage.output_tokens,
            prompt_token_count=response.usage.input_tokens,
        )
    logger.info(
        "Anthropic response.",
        response=response,
    )

    return LLMResponse(
        text="{" + " ".join(res.text for res in response.content) + "}",
        metadata=metadata,
    )


async def anthropic_inference(request: LLMRequest) -> LLMResponse:
    """Infer the response to the message"""
    content = [
        {
            "role": "user",
            "content": text,
        }
        for text in request.content
        if isinstance(text, str)
    ]
    response = await get_inference_response(request, content)
    try:
        json.loads(response.text)
    except json.JSONDecodeError as e:
        logger.error(
            "Failed to decode response",
            response=response.text,
            exc_info=e,
        )
        content.append(
            {
                "role": "user",
                "content": f"Your previos response was: {response.text}, but I failed to decode it due to an error: {e}. Please respond using valid json.",
            }
        )
        new_response = await get_inference_response(request, content)
        json.loads(new_response.text)
        combined_metadata = LLMResponseMetadata(
            total_token_count=response.metadata.total_token_count
            + new_response.metadata.total_token_count,
            cached_content_token_count=response.metadata.cached_content_token_count
            + new_response.metadata.cached_content_token_count,
            candidates_token_count=response.metadata.candidates_token_count
            + new_response.metadata.candidates_token_count,
            prompt_token_count=response.metadata.prompt_token_count
            + new_response.metadata.prompt_token_count,
        )
        response = LLMResponse(
            text=new_response.text,
            metadata=combined_metadata,
        )

    return response
