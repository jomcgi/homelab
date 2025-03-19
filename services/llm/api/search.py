from duckduckgo_search.duckduckgo_search_async import AsyncDDGS
import google.generativeai as genai
from google.generativeai.types.safety_types import HarmBlockThreshold, HarmCategory
from pydantic_settings import BaseSettings, SettingsConfigDict
import structlog
import opentelemetry.trace as trace
from api.types import InputMediaContent, LLMResponse
from api.gemini import gemini_inference
from api.instrumentation import _add_to_current_span

logger = structlog.get_logger(__name__)


class GeminiConfig(BaseSettings):
    API_KEY: str
    MODEL_NAME: str = "gemini-1.5-flash"

    model_config = SettingsConfigDict(
        env_prefix="GEMINI_",
    )


GROUNDING_PROMPT = """
You are an answer-optimization system that transforms conversations into a single targeted question to retrieve instant answers. Your output must be EXACTLY one line containing either a direct question or a bang-prefixed query.
Instructions for question generation:
Analyze the provided conversation to identify:

The core information need
The most appropriate knowledge domain
The specific type of answer needed (factual, how-to, definition, etc.)
Any contextual clues that could make the question more precise

Generate ONE optimized question that:

Uses natural question phrasing
Is specific enough to get an instant answer
Captures the complete information need

Question formatting rules:

MUST be a single line
ONE question only
5-20 words in length
Use quotes only for exact phrase matching
NO period at the end
NO multiple questions with OR

Example 1:
Input:
User: "How do electric cars store energy?"
Assistant: "Electric cars primarily use lithium-ion batteries to store energy. These batteries can be recharged when plugged into a charging station."
Output:
How do lithium ion batteries store and discharge energy in electric vehicles
Example 2:
Input:
User: "What's causing my tomato plants to have yellow leaves?"
Assistant: "Yellow leaves on tomato plants often indicate either overwatering, nutrient deficiency, or disease. The most common issues are nitrogen deficiency or early blight. Check if the yellowing starts from the bottom leaves and moves up."
Output:
what causes yellow leaves starting from bottom of tomato plants
Wrong outputs:
❌ [Query: how do batteries work] (no labels)
❌ what are electric cars? OR how do they work (no multiple questions)
❌ "how do batteries work?" (unnecessary quotes)
❌ what causes yellow leaves. (no period)
Special considerations:

Use complete sentences with proper question structure
Include relevant technical terms when appropriate
Specify units for measurement-related questions
Add context if it helps narrow down the answer
"""

SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}
GEMINI_CONFIG = GeminiConfig()
genai.configure(api_key=GEMINI_CONFIG.API_KEY)


async def get_search_context(content: list[InputMediaContent | str]) -> LLMResponse:
    """Get search context from formatted content"""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("llm.api.retrieve_context"):
        question = await gemini_inference(content, GROUNDING_PROMPT)
        _add_to_current_span({"llm.api.retrieve_context.question": question.text})
        async with AsyncDDGS() as client:
            context = await client.atext(question.text, safesearch="off", max_results=3)
            return LLMResponse(
                text=str(context),
                metadata=question.metadata,
            )
