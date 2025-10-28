"""Type-safe client for Obsidian Local REST API with path restrictions."""

import json
import logging
from pathlib import Path
from types import TracebackType
from typing import Any

import httpx
from opentelemetry import trace

from services.n8n_obsidian_api.app.models import (
    NoteJson,
    NoteStat,
    PatchOperation,
    PatchTargetType,
    generated,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class PathRestrictionError(Exception):
    """Raised when attempting to write outside allowed paths."""

    pass


class ObsidianClient:
    """
    Type-safe client for Obsidian Local REST API via Cloudflare Tunnel.

    Uses Cloudflare service tokens to bypass Cloudflare Access authentication.
    Cloudflare Access then injects Obsidian API credentials automatically.

    Enforces path restrictions:
    - Write operations (PUT, POST, PATCH, DELETE) only allowed in /n8n/
    - Read operations (GET) allowed anywhere in the vault
    """

    WRITE_ALLOWED_PREFIX = "n8n/"
    CONTENT_TYPE_JSON = "application/vnd.olrapi.note+json"
    CONTENT_TYPE_MARKDOWN = "text/markdown"

    def __init__(
        self,
        base_url: str,
        cloudflare_client_id: str,
        cloudflare_client_secret: str,
        timeout: float = 30.0,
    ):
        """
        Initialize Obsidian API client.

        Args:
            base_url: Base URL of Obsidian API via Cloudflare Tunnel (e.g., "https://obsidian.jomcgi.dev")
            cloudflare_client_id: Cloudflare service token client ID
            cloudflare_client_secret: Cloudflare service token client secret
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "CF-Access-Client-Id": cloudflare_client_id,
                "CF-Access-Client-Secret": cloudflare_client_secret,
            },
            timeout=timeout,
        )

    async def __aenter__(self) -> "ObsidianClient":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    def _validate_write_path(self, path: str) -> None:
        """
        Validate that a path is allowed for write operations.

        Args:
            path: File path relative to vault root

        Raises:
            PathRestrictionError: If path is not in allowed write directory
        """
        # Normalize the path
        normalized = Path(path).as_posix()

        # Remove leading slashes
        normalized = normalized.lstrip("/")

        if not normalized.startswith(self.WRITE_ALLOWED_PREFIX):
            raise PathRestrictionError(
                f"Write operations only allowed in /{self.WRITE_ALLOWED_PREFIX} (attempted: {path})"
            )

    @tracer.start_as_current_span("obsidian.get_note")
    async def get_note(self, path: str, as_json: bool = True) -> NoteJson | str:
        """
        Read a note from the vault.

        Args:
            path: Path to note relative to vault root
            as_json: If True, return structured NoteJson; if False, return raw markdown

        Returns:
            NoteJson object if as_json=True, else markdown string

        Raises:
            httpx.HTTPStatusError: If note doesn't exist or other API error
        """
        span = trace.get_current_span()
        span.set_attribute("obsidian.path", path)
        span.set_attribute("obsidian.operation", "read")

        headers = {}
        if as_json:
            headers["Accept"] = self.CONTENT_TYPE_JSON

        response = await self._client.get(f"/vault/{path}", headers=headers)
        response.raise_for_status()

        if as_json:
            # Parse with generated model for type-safe validation
            api_response = generated.NoteJson(**response.json())
            # Convert to public model (both have same structure currently)
            return NoteJson(
                path=api_response.path,
                content=api_response.content,
                tags=api_response.tags,
                frontmatter=api_response.frontmatter,
                stat=NoteStat(
                    ctime=api_response.stat.ctime,
                    mtime=api_response.stat.mtime,
                    size=int(api_response.stat.size),
                ),
            )
        return response.text

    @tracer.start_as_current_span("obsidian.create_or_update_note")
    async def create_or_update_note(self, path: str, content: str) -> None:
        """
        Create a new note or update an existing one.

        Args:
            path: Path to note relative to vault root (must be in /n8n/)
            content: Markdown content

        Raises:
            PathRestrictionError: If path is not in /n8n/
            httpx.HTTPStatusError: If API request fails
        """
        self._validate_write_path(path)

        span = trace.get_current_span()
        span.set_attribute("obsidian.path", path)
        span.set_attribute("obsidian.operation", "create_or_update")

        response = await self._client.put(
            f"/vault/{path}",
            content=content,
            headers={"Content-Type": self.CONTENT_TYPE_MARKDOWN},
        )
        response.raise_for_status()

    @tracer.start_as_current_span("obsidian.append_to_note")
    async def append_to_note(self, path: str, content: str) -> None:
        """
        Append content to an existing note or create if it doesn't exist.

        Args:
            path: Path to note relative to vault root (must be in /n8n/)
            content: Markdown content to append

        Raises:
            PathRestrictionError: If path is not in /n8n/
            httpx.HTTPStatusError: If API request fails
        """
        self._validate_write_path(path)

        span = trace.get_current_span()
        span.set_attribute("obsidian.path", path)
        span.set_attribute("obsidian.operation", "append")

        response = await self._client.post(
            f"/vault/{path}",
            content=content,
            headers={"Content-Type": self.CONTENT_TYPE_MARKDOWN},
        )
        response.raise_for_status()

    @tracer.start_as_current_span("obsidian.patch_note")
    async def patch_note(
        self,
        path: str,
        content: str,
        operation: PatchOperation,
        target_type: PatchTargetType,
        target: str,
    ) -> None:
        """
        Patch a note relative to a heading, block, or frontmatter field.

        Args:
            path: Path to note relative to vault root (must be in /n8n/)
            content: Content to insert
            operation: append, prepend, or replace
            target_type: heading, block, or frontmatter
            target: Target identifier (heading name, block ID, or frontmatter key)

        Raises:
            PathRestrictionError: If path is not in /n8n/
            httpx.HTTPStatusError: If API request fails
        """
        self._validate_write_path(path)

        span = trace.get_current_span()
        span.set_attribute("obsidian.path", path)
        span.set_attribute("obsidian.operation", "patch")
        span.set_attribute("obsidian.patch.operation", operation.value)
        span.set_attribute("obsidian.patch.target_type", target_type.value)

        response = await self._client.patch(
            f"/vault/{path}",
            content=content,
            headers={
                "Content-Type": self.CONTENT_TYPE_MARKDOWN,
                "Operation": operation.value,
                "Target-Type": target_type.value,
                "Target": target,
            },
        )
        response.raise_for_status()

    @tracer.start_as_current_span("obsidian.delete_note")
    async def delete_note(self, path: str) -> None:
        """
        Delete a note from the vault.

        Args:
            path: Path to note relative to vault root (must be in /n8n/)

        Raises:
            PathRestrictionError: If path is not in /n8n/
            httpx.HTTPStatusError: If note doesn't exist or API request fails
        """
        self._validate_write_path(path)

        span = trace.get_current_span()
        span.set_attribute("obsidian.path", path)
        span.set_attribute("obsidian.operation", "delete")

        response = await self._client.delete(f"/vault/{path}")
        response.raise_for_status()

    @tracer.start_as_current_span("obsidian.update_frontmatter")
    async def update_frontmatter(self, path: str, key: str, value: Any) -> None:
        """
        Update a single frontmatter field in a note.

        Args:
            path: Path to note relative to vault root (must be in /n8n/)
            key: Frontmatter field key
            value: Value to set (will be JSON-serialized)

        Raises:
            PathRestrictionError: If path is not in /n8n/
            httpx.HTTPStatusError: If API request fails
        """
        self._validate_write_path(path)

        span = trace.get_current_span()
        span.set_attribute("obsidian.path", path)
        span.set_attribute("obsidian.operation", "update_frontmatter")
        span.set_attribute("obsidian.frontmatter.key", key)

        response = await self._client.patch(
            f"/vault/{path}",
            content=json.dumps(value),
            headers={
                "Content-Type": "application/json",
                "Operation": "replace",
                "Target-Type": "frontmatter",
                "Target": key,
            },
        )
        response.raise_for_status()

    @tracer.start_as_current_span("obsidian.list_vault")
    async def list_vault(self) -> list[str]:
        """
        List all files in the vault.

        Returns:
            List of file paths relative to vault root

        Raises:
            httpx.HTTPStatusError: If API request fails
        """
        span = trace.get_current_span()
        span.set_attribute("obsidian.operation", "list_vault")

        response = await self._client.get("/vault/")
        response.raise_for_status()

        data = response.json()

        # The response format may vary, handle both array and object formats
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "files" in data:
            return data["files"]
        else:
            logger.warning(f"Unexpected list_vault response format: {type(data)}")
            return []
