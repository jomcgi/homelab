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


async def anthropic_inference(request: LLMRequest) -> LLMResponse:
    """Infer the response to the message"""
    tracer = trace.get_tracer(__name__)
    content = [
        {
            "role": "user",
            "content": text,
        }
        for text in request.content
        if isinstance(text, str)
    ]
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
            max_tokens=2000,
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

    reply = "{" + " ".join(res.text for res in response.content) + "}"

    return LLMResponse(
        text=reply,
        metadata=metadata,
    )
