"""Extra coverage for embedding.py -- malformed JSON, missing keys, empty data array."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat.embedding import EmbeddingClient


@pytest.fixture
def client():
    return EmbeddingClient(base_url="http://fake:8080")


def _make_ok_response(body: dict) -> MagicMock:
    """Build a fake httpx response with raise_for_status as a no-op and given JSON body."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = body
    return resp


def _make_json_error_response() -> MagicMock:
    """Build a fake httpx response whose json() method raises JSONDecodeError."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.side_effect = json.JSONDecodeError("Expecting value", doc="<html>", pos=0)
    return resp


# ---------------------------------------------------------------------------
# embed() -- malformed JSON body (200 OK but resp.json() raises)
# ---------------------------------------------------------------------------


class TestEmbedMalformedJson:
    @pytest.mark.asyncio
    async def test_raises_on_malformed_json(self, client):
        """embed() propagates JSONDecodeError when the response body is not valid JSON."""
        fake_response = _make_json_error_response()

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_cls.return_value = mock_client

            with pytest.raises(json.JSONDecodeError):
                await client.embed("test input")

    @pytest.mark.asyncio
    async def test_json_error_is_value_error_subclass(self, client):
        """JSONDecodeError is a subclass of ValueError -- ensure it's not silently swallowed."""
        fake_response = _make_json_error_response()

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_cls.return_value = mock_client

            with pytest.raises(ValueError):
                await client.embed("another input")


# ---------------------------------------------------------------------------
# embed() -- missing 'data' key in otherwise valid JSON
# ---------------------------------------------------------------------------


class TestEmbedMissingDataKey:
    @pytest.mark.asyncio
    async def test_raises_key_error_when_data_key_absent(self, client):
        """embed() raises KeyError when the JSON body has no 'data' key."""
        fake_response = _make_ok_response({"error": "model not loaded"})

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_cls.return_value = mock_client

            with pytest.raises(KeyError):
                await client.embed("hello")

    @pytest.mark.asyncio
    async def test_raises_key_error_when_embedding_key_absent(self, client):
        """embed() raises KeyError when 'data[0]' exists but has no 'embedding' key."""
        fake_response = _make_ok_response({"data": [{"index": 0}]})  # no 'embedding'

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_cls.return_value = mock_client

            with pytest.raises(KeyError):
                await client.embed("hello")


# ---------------------------------------------------------------------------
# embed() -- empty 'data' array (valid JSON structure but no elements)
# ---------------------------------------------------------------------------


class TestEmbedEmptyDataArray:
    @pytest.mark.asyncio
    async def test_raises_index_error_when_data_is_empty(self, client):
        """embed() raises IndexError when 'data' is an empty list."""
        fake_response = _make_ok_response({"data": []})

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_cls.return_value = mock_client

            with pytest.raises(IndexError):
                await client.embed("no vectors here")

    @pytest.mark.asyncio
    async def test_raises_index_error_not_key_error_for_empty_data(self, client):
        """The exception is specifically IndexError (list index out of range), not KeyError."""
        fake_response = _make_ok_response({"data": []})

        with patch("chat.embedding.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = fake_response
            mock_cls.return_value = mock_client

            try:
                await client.embed("empty")
                pytest.fail("Expected IndexError was not raised")
            except IndexError:
                pass  # correct exception type
            except KeyError:
                pytest.fail("Got KeyError instead of expected IndexError")
