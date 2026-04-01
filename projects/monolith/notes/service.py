"""Notes service — proxies fleeting note creation to vault-mcp."""

import os

import httpx

VAULT_API_URL = os.environ.get("VAULT_API_URL", "")


async def create_fleeting_note(content: str) -> dict:
    """Send a fleeting note to the vault-mcp API."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp = await client.post(  # nosemgrep: tainted-fastapi-http-request-httpx
            f"{VAULT_API_URL}/api/notes",
            json={"content": content, "source": "web-ui"},
        )
        resp.raise_for_status()
        return resp.json()
