"""Additional coverage for MessageStore -- search_similar() with mocked Session."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

import pytest

from chat.models import Message
from chat.store import MessageStore


def _make_message(
    id: int,
    channel_id: str = "ch1",
    user_id: str = "u1",
    content: str = "hello",
) -> Message:
    return Message(
        id=id,
        discord_message_id=str(id),
        channel_id=channel_id,
        user_id=user_id,
        username="Alice",
        content=content,
        is_bot=False,
        embedding=[0.0] * 1024,
        created_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def store(mock_session):
    embed_client = AsyncMock()
    embed_client.embed.return_value = [0.0] * 1024
    return MessageStore(session=mock_session, embed_client=embed_client)


class TestSearchSimilar:
    def test_returns_messages_from_exec(self, store, mock_session):
        """search_similar returns Message objects produced by session.exec."""
        msg = _make_message(id=1)
        mock_session.exec.return_value = [msg]

        results = store.search_similar(
            channel_id="ch1",
            query_embedding=[0.1] * 1024,
        )

        assert results == [msg]
        mock_session.exec.assert_called_once()

    def test_returns_empty_list_when_no_results(self, store, mock_session):
        """search_similar returns an empty list when exec yields nothing."""
        mock_session.exec.return_value = []

        results = store.search_similar(
            channel_id="ch1",
            query_embedding=[0.0] * 1024,
        )

        assert results == []

    def test_exclude_ids_are_passed_as_params(self, store, mock_session):
        """When exclude_ids is provided the SQL params include excl_0, excl_1, …."""
        mock_session.exec.return_value = []

        store.search_similar(
            channel_id="ch1",
            query_embedding=[0.0] * 1024,
            exclude_ids=[10, 20],
        )

        call_kwargs = mock_session.exec.call_args
        params = call_kwargs[1]["params"]
        assert params.get("excl_0") == 10
        assert params.get("excl_1") == 20

    def test_user_id_filter_included_in_params(self, store, mock_session):
        """When user_id is provided it is included in the SQL params."""
        mock_session.exec.return_value = []

        store.search_similar(
            channel_id="ch1",
            query_embedding=[0.0] * 1024,
            user_id="u42",
        )

        call_kwargs = mock_session.exec.call_args
        params = call_kwargs[1]["params"]
        assert params.get("user_id") == "u42"

    def test_no_user_id_filter_when_not_provided(self, store, mock_session):
        """When user_id is not provided there is no user_id key in the params."""
        mock_session.exec.return_value = []

        store.search_similar(
            channel_id="ch1",
            query_embedding=[0.0] * 1024,
        )

        call_kwargs = mock_session.exec.call_args
        params = call_kwargs[1]["params"]
        assert "user_id" not in params

    def test_channel_id_always_in_params(self, store, mock_session):
        """channel_id is always included in the SQL params."""
        mock_session.exec.return_value = []

        store.search_similar(
            channel_id="my-channel",
            query_embedding=[0.0] * 1024,
        )

        call_kwargs = mock_session.exec.call_args
        params = call_kwargs[1]["params"]
        assert params["channel_id"] == "my-channel"

    def test_limit_param_is_passed(self, store, mock_session):
        """The limit parameter is forwarded to the SQL query."""
        mock_session.exec.return_value = []

        store.search_similar(
            channel_id="ch1",
            query_embedding=[0.0] * 1024,
            limit=3,
        )

        call_kwargs = mock_session.exec.call_args
        params = call_kwargs[1]["params"]
        assert params["limit"] == 3

    def test_exclude_ids_empty_list_treated_as_no_exclusions(self, store, mock_session):
        """Passing exclude_ids=[] produces no excl_ params (no NOT IN clause)."""
        mock_session.exec.return_value = []

        store.search_similar(
            channel_id="ch1",
            query_embedding=[0.0] * 1024,
            exclude_ids=[],
        )

        call_kwargs = mock_session.exec.call_args
        params = call_kwargs[1]["params"]
        excl_keys = [k for k in params if k.startswith("excl_")]
        assert excl_keys == []
