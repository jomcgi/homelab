"""Tests for network-level failure paths in notes/service.py.

The coverage review identified two untested paths:
  1. ``httpx.ConnectError`` raised during ``client.post()``
  2. ``httpx.ReadTimeout`` raised during ``client.post()``
  3. Empty ``VAULT_API_URL`` default (module-level constant reads ``""`` when env
     var is unset, causing the request to target ``/api/notes`` with no host)

All three paths are covered here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

import notes.service
from notes.service import create_fleeting_note


# ---------------------------------------------------------------------------
# Network-error paths
# ---------------------------------------------------------------------------


class TestCreateFleetingNoteNetworkErrors:
    """ConnectError and ReadTimeout must propagate out of create_fleeting_note."""

    @pytest.mark.asyncio
    async def test_connect_error_propagates(self, monkeypatch):
        """httpx.ConnectError raised by client.post() propagates to the caller."""
        monkeypatch.setattr(notes.service, "VAULT_API_URL", "http://vault-mcp:8000")

        with patch("notes.service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(
                side_effect=httpx.ConnectError("connection refused")
            )

            with pytest.raises(httpx.ConnectError):
                await create_fleeting_note("hello")

    @pytest.mark.asyncio
    async def test_read_timeout_propagates(self, monkeypatch):
        """httpx.ReadTimeout raised by client.post() propagates to the caller."""
        monkeypatch.setattr(notes.service, "VAULT_API_URL", "http://vault-mcp:8000")

        with patch("notes.service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(
                side_effect=httpx.ReadTimeout("read timed out")
            )

            with pytest.raises(httpx.ReadTimeout):
                await create_fleeting_note("hello")

    @pytest.mark.asyncio
    async def test_connect_error_does_not_return_value(self, monkeypatch):
        """create_fleeting_note never returns a value when ConnectError is raised."""
        monkeypatch.setattr(notes.service, "VAULT_API_URL", "http://vault-mcp:8000")

        with patch("notes.service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(
                side_effect=httpx.ConnectError("no route to host")
            )

            result = None
            try:
                result = await create_fleeting_note("test")
            except httpx.ConnectError:
                pass

        assert result is None


# ---------------------------------------------------------------------------
# Empty VAULT_API_URL default
# ---------------------------------------------------------------------------


class TestVaultApiUrlDefault:
    """When VAULT_API_URL is empty (the module default), the URL constructed
    for the POST request starts with ``/api/notes`` (no host prefix)."""

    @pytest.mark.asyncio
    async def test_empty_vault_url_uses_relative_path(self, monkeypatch):
        """With VAULT_API_URL='', the request URL is '/api/notes'."""
        monkeypatch.setattr(notes.service, "VAULT_API_URL", "")

        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None

        with patch("notes.service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(return_value=mock_response)

            await create_fleeting_note("test content")

        call_args = MockClient.return_value.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url")
        # With VAULT_API_URL="" the service builds "" + "/api/notes"
        assert url == "/api/notes"
