from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from notes.service import create_fleeting_note


class TestCreateFleetingNote:
    @pytest.mark.asyncio
    async def test_posts_to_vault_api(self, monkeypatch):
        monkeypatch.setenv("VAULT_API_URL", "http://vault-mcp:8000")
        # Need to reimport to pick up env var
        import notes.service

        monkeypatch.setattr(notes.service, "VAULT_API_URL", "http://vault-mcp:8000")

        # raise_for_status and json are called synchronously in service.py (no await)
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"path": "Fleeting/2026-03-31 1423.md"}
        mock_response.raise_for_status.return_value = None

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

    @pytest.mark.asyncio
    async def test_raises_on_vault_error(self, monkeypatch):
        monkeypatch.setenv("VAULT_API_URL", "http://vault-mcp:8000")
        import notes.service

        monkeypatch.setattr(notes.service, "VAULT_API_URL", "http://vault-mcp:8000")

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=mock_response
        )

        with patch("notes.service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(return_value=mock_response)

            with pytest.raises(httpx.HTTPStatusError):
                await create_fleeting_note("test")

    @pytest.mark.asyncio
    async def test_posts_correct_source_field(self, monkeypatch):
        """The source field must always be 'web-ui' regardless of content."""
        import notes.service

        monkeypatch.setattr(notes.service, "VAULT_API_URL", "http://vault-mcp:8000")

        mock_response = MagicMock()
        mock_response.json.return_value = {"path": "Fleeting/note.md"}
        mock_response.raise_for_status.return_value = None

        with patch("notes.service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(return_value=mock_response)

            await create_fleeting_note("any content")

        call_kwargs = MockClient.return_value.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["source"] == "web-ui"
        assert payload["content"] == "any content"

    @pytest.mark.asyncio
    async def test_returns_json_response_body(self, monkeypatch):
        """create_fleeting_note returns the parsed JSON body from the vault API."""
        import notes.service

        monkeypatch.setattr(notes.service, "VAULT_API_URL", "http://vault-mcp:8000")

        expected = {"path": "Fleeting/2026-01-01 0000.md", "id": "abc123"}
        mock_response = MagicMock()
        mock_response.json.return_value = expected
        mock_response.raise_for_status.return_value = None

        with patch("notes.service.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.post = AsyncMock(return_value=mock_response)

            result = await create_fleeting_note("hello")

        assert result == expected

    @pytest.mark.asyncio
    async def test_uses_vault_api_url_env_var(self, monkeypatch):
        """The VAULT_API_URL env var is used to construct the endpoint URL."""
        import notes.service

        monkeypatch.setattr(notes.service, "VAULT_API_URL", "http://custom-vault:9999")

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
        assert url == "http://custom-vault:9999/api/notes"
