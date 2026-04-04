"""Extra coverage for store.py -- get_recent() with an empty channel."""

from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from chat.store import MessageStore


@pytest.fixture(name="session")
def session_fixture():
    """In-memory SQLite session (schema-stripped for SQLite compat)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_schemas = {}
    for table in SQLModel.metadata.tables.values():
        if table.schema is not None:
            original_schemas[table.name] = table.schema
            table.schema = None

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

    for table in SQLModel.metadata.tables.values():
        if table.name in original_schemas:
            table.schema = original_schemas[table.name]


@pytest.fixture
def store(session):
    embed_client = AsyncMock()
    embed_client.embed.return_value = [0.0] * 512
    return MessageStore(session=session, embed_client=embed_client)


class TestGetRecentEmptyChannel:
    def test_returns_empty_list_for_channel_with_no_messages(self, store):
        """get_recent() returns [] when no messages exist for the given channel."""
        result = store.get_recent("channel-with-no-messages", limit=20)
        assert result == []

    def test_returns_empty_list_for_nonexistent_channel(self, store):
        """get_recent() returns [] for a channel ID that has never received a message."""
        result = store.get_recent("nonexistent-channel-xyz", limit=5)
        assert isinstance(result, list)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# search_similar() -- error paths with mocked session
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    from unittest.mock import MagicMock

    return MagicMock()


@pytest.fixture
def mock_store(mock_session):
    embed_client = AsyncMock()
    embed_client.embed.return_value = [0.0] * 512
    return MessageStore(session=mock_session, embed_client=embed_client)


class TestSearchSimilarErrorPaths:
    def test_propagates_exception_from_session_exec(self, mock_store, mock_session):
        """search_similar propagates exceptions raised by session.exec()."""
        mock_session.exec.side_effect = RuntimeError("DB connection lost")

        with pytest.raises(RuntimeError, match="DB connection lost"):
            mock_store.search_similar(
                channel_id="ch1",
                query_embedding=[0.0] * 512,
            )

    def test_propagates_operational_error_from_exec(self, mock_store, mock_session):
        """search_similar propagates OperationalError (e.g. malformed SQL / schema issue)."""
        from sqlalchemy.exc import OperationalError

        mock_session.exec.side_effect = OperationalError(
            "no such table: chat.messages", params=None, orig=None
        )

        with pytest.raises(OperationalError):
            mock_store.search_similar(
                channel_id="ch-missing",
                query_embedding=[0.1] * 512,
            )

    def test_large_exclude_ids_builds_all_placeholders(self, mock_store, mock_session):
        """search_similar with 50 exclude_ids creates excl_0 … excl_49 params."""
        mock_session.exec.return_value = []

        large_ids = list(range(50))
        mock_store.search_similar(
            channel_id="ch1",
            query_embedding=[0.0] * 512,
            exclude_ids=large_ids,
        )

        call_kwargs = mock_session.exec.call_args
        params = call_kwargs[1]["params"]
        for i in range(50):
            assert f"excl_{i}" in params, f"Missing excl_{i} in params"
            assert params[f"excl_{i}"] == i

    def test_large_exclude_ids_sql_contains_not_in_clause(
        self, mock_store, mock_session
    ):
        """The generated SQL string contains NOT IN when exclude_ids are provided."""
        mock_session.exec.return_value = []

        mock_store.search_similar(
            channel_id="ch1",
            query_embedding=[0.0] * 512,
            exclude_ids=[1, 2, 3],
        )

        sql_obj = mock_session.exec.call_args[0][0]
        # sqlalchemy text() objects render their clause string via str()
        assert "NOT IN" in str(sql_obj).upper()

    def test_search_similar_with_zero_exclude_ids_no_not_in_clause(
        self, mock_store, mock_session
    ):
        """When exclude_ids is empty the SQL does NOT contain a NOT IN clause."""
        mock_session.exec.return_value = []

        mock_store.search_similar(
            channel_id="ch1",
            query_embedding=[0.0] * 512,
            exclude_ids=[],
        )

        sql_obj = mock_session.exec.call_args[0][0]
        assert "NOT IN" not in str(sql_obj).upper()
