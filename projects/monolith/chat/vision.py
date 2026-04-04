"""Vision client -- calls Gemma 4 via llama.cpp /v1/chat/completions for image description."""

import base64
import os

import httpx

LLAMA_CPP_URL = os.environ.get("LLAMA_CPP_URL", "")

VISION_SYSTEM_PROMPT = (
    "Describe this image concisely for semantic search. "
    "Focus on the key subjects, actions, and notable details."
)


class VisionClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or LLAMA_CPP_URL

    async def describe(self, image_bytes: bytes, content_type: str) -> str:
        """Describe an image using Gemma 4 vision, returning a text summary."""
        b64 = base64.b64encode(image_bytes).decode()
        data_uri = f"data:{content_type};base64,{b64}"

        payload = {
            "model": "gemma-4-26b-a4b",
            "messages": [
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image."},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                },
            ],
            "max_tokens": 256,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            try:
                return resp.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as e:
                raise ValueError(f"unexpected vision response shape: {e}") from e
