import aiohttp
from pydantic import BaseModel
from fastapi import HTTPException
import structlog
from api.instrumentation import _add_to_current_span

logger = structlog.get_logger(__name__)


class MediaContent(BaseModel):
    """Accepted media content types"""

    data: bytes
    mime_type: str


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


class InputMediaContent(BaseModel):
    """Input media content"""

    url: str
    mime_type: str

    async def retrieve_data(
        self, session: aiohttp.ClientSession
    ) -> dict[str, str | bytes]:
        return MediaContent(
            data=await get_content_from_url(session, self.url),
            mime_type=self.mime_type,
        ).model_dump()


class LLMResponseMetadata(BaseModel):
    """Response metadata for LLM inference"""

    total_token_count: int
    cached_content_token_count: int
    candidates_token_count: int
    prompt_token_count: int

    def model_post_init(self, __context) -> None:
        _add_to_current_span(
            {
                "gen_ai.response.total_token_count": str(self.total_token_count),
                "gen_ai.response.cached_content_token_count": str(
                    self.cached_content_token_count
                ),
                "gen_ai.response.candidates_token_count": str(
                    self.candidates_token_count
                ),
                "gen_ai.response.prompt_token_count": str(self.prompt_token_count),
            }
        )
        logger.info(
            "LLM response metadata.",
            total_token_count=self.total_token_count,
            cached_content_token_count=self.cached_content_token_count,
            candidates_token_count=self.candidates_token_count,
            prompt_token_count=self.prompt_token_count,
        )


class LLMResponse(BaseModel):
    """Response class for LLM inference"""

    text: str
    metadata: LLMResponseMetadata


class LLMRequest(BaseModel):
    prompt: str
    content: list[str | InputMediaContent]
