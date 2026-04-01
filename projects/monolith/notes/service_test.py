from unittest.mock import AsyncMock, patch

import httpx
import pytest

from notes.service import create_fleeting_note


class TestCreateFleetingNote:
    async def test_posts_to_vault_api(self, monkeypatch):
        monkeypatch.setenv("VAULT_API_URL", "http://vault-mcp:8000")
        # Need to reimport to pick up env var
        import notes.service

        monkeypatch.setattr(notes.service, "VAULT_API_URL", "http://vault-mcp:8000")

        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"path": "Fleeting/2026-03-31 1423.md"}
        mock_response.raise_for_status = AsyncMock()

        with patch("notes.service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(return_value=mock_response)

            result = await create_fleeting_note("My thought")

        MockClient.return_value.post.assert_called_once_with(
            "http://vault-mcp:8000/api/notes",
            json={"content": "My thought", "source": "web-ui"},
        )
        assert result == {"path": "Fleeting/2026-03-31 1423.md"}

    async def test_raises_on_vault_error(self, monkeypatch):
        monkeypatch.setenv("VAULT_API_URL", "http://vault-mcp:8000")
        import notes.service

        monkeypatch.setattr(notes.service, "VAULT_API_URL", "http://vault-mcp:8000")

        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=AsyncMock(), response=mock_response
        )

        with patch("notes.service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(return_value=mock_response)

            with pytest.raises(httpx.HTTPStatusError):
                await create_fleeting_note("test")
