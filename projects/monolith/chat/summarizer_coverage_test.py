"""Additional coverage for summarizer -- build_llm_caller() and error handling."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from chat.models import Message, UserChannelSummary
from chat.summarizer import build_llm_caller, generate_summaries


# ---------------------------------------------------------------------------
# Session fixture (in-memory SQLite)
# ---------------------------------------------------------------------------


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


def _make_message(session, channel_id, user_id, username, content, msg_id):
    msg = Message(
        id=msg_id,
        discord_message_id=str(msg_id),
        channel_id=channel_id,
        user_id=user_id,
        username=username,
        content=content,
        is_bot=False,
        embedding=[0.0] * 1024,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return msg


# ---------------------------------------------------------------------------
# TestBuildLlmCaller -- factory function
# ---------------------------------------------------------------------------


class TestBuildLlmCaller:
    @pytest.mark.asyncio
    async def test_sends_correct_payload(self):
        """build_llm_caller() sends model, messages, and max_tokens in the request."""
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Summary text"}}]
        }
        mock_instance.post = AsyncMock(return_value=mock_response)

        with patch("chat.summarizer.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_instance
            caller = build_llm_caller("http://fake:8080")
            result = await caller("Summarize this conversation.")

        assert result == "Summary text"
        mock_instance.post.assert_called_once()
        call_kwargs = mock_instance.post.call_args
        url_arg = call_kwargs[0][0] if call_kwargs[0] else call_kwargs.kwargs.get("url")
        assert url_arg == "http://fake:8080/v1/chat/completions"
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["model"] == "gemma-4-26b-a4b"
        assert payload["messages"][0]["role"] == "user"
        assert payload["messages"][0]["content"] == "Summarize this conversation."
        assert payload["max_tokens"] == 256

    @pytest.mark.asyncio
    async def test_raises_runtime_error_on_missing_choices(self):
        """build_llm_caller() raises RuntimeError when 'choices' key is absent."""
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"unexpected": "shape"}
        mock_instance.post = AsyncMock(return_value=mock_response)

        with patch("chat.summarizer.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_instance
            caller = build_llm_caller("http://fake:8080")
            with pytest.raises(RuntimeError, match="unexpected LLM response shape"):
                await caller("some prompt")

    @pytest.mark.asyncio
    async def test_raises_runtime_error_on_empty_choices(self):
        """build_llm_caller() raises RuntimeError when 'choices' list is empty."""
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"choices": []}
        mock_instance.post = AsyncMock(return_value=mock_response)

        with patch("chat.summarizer.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_instance
            caller = build_llm_caller("http://fake:8080")
            with pytest.raises(RuntimeError, match="unexpected LLM response shape"):
                await caller("some prompt")

    @pytest.mark.asyncio
    async def test_raises_runtime_error_on_missing_content(self):
        """build_llm_caller() raises RuntimeError when 'content' key is missing."""
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant"}}]
        }
        mock_instance.post = AsyncMock(return_value=mock_response)

        with patch("chat.summarizer.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_instance
            caller = build_llm_caller("http://fake:8080")
            with pytest.raises(RuntimeError, match="unexpected LLM response shape"):
                await caller("some prompt")

    @pytest.mark.asyncio
    async def test_uses_env_url_when_base_url_not_provided(self):
        """build_llm_caller() uses LLAMA_CPP_URL env var when base_url is None."""
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_instance.post = AsyncMock(return_value=mock_response)

        with patch("chat.summarizer.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_instance
            with patch(
                "chat.summarizer.os.environ.get", return_value="http://env:9090"
            ):
                caller = build_llm_caller()
                await caller("prompt")

        call_url = mock_instance.post.call_args[0][0]
        assert "http://env:9090" in call_url

    @pytest.mark.asyncio
    async def test_propagates_http_status_error(self):
        """build_llm_caller() propagates HTTPStatusError from raise_for_status()."""
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=MagicMock(),
            response=MagicMock(),
        )
        mock_instance.post = AsyncMock(return_value=mock_response)

        with patch("chat.summarizer.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_instance
            caller = build_llm_caller("http://fake:8080")
            with pytest.raises(httpx.HTTPStatusError):
                await caller("some prompt")


# ---------------------------------------------------------------------------
# TestGenerateSummariesErrorHandling -- per-pair error isolation
# ---------------------------------------------------------------------------


class TestGenerateSummariesErrorHandling:
    @pytest.mark.asyncio
    async def test_continues_to_next_pair_when_one_raises(self, session):
        """generate_summaries() skips a failing pair and processes the next one."""
        _make_message(session, "ch1", "u1", "Alice", "Hello world", 1)
        _make_message(session, "ch2", "u2", "Bob", "Goodbye world", 2)

        call_order = []

        async def flaky_llm(prompt: str) -> str:
            if "Alice" in prompt:
                call_order.append("alice_fail")
                raise RuntimeError("LLM exploded for Alice")
            call_order.append("bob_ok")
            return "Bob talked about goodbyes."

        await generate_summaries(session, flaky_llm)

        # Alice's summary should not have been created (exception was raised)
        alice_summary = session.exec(
            select(UserChannelSummary).where(UserChannelSummary.user_id == "u1")
        ).first()
        assert alice_summary is None

        # Bob's summary should have been created despite Alice's failure
        bob_summary = session.exec(
            select(UserChannelSummary).where(UserChannelSummary.user_id == "u2")
        ).first()
        assert bob_summary is not None
        assert bob_summary.summary == "Bob talked about goodbyes."

    @pytest.mark.asyncio
    async def test_processes_multiple_channel_user_pairs(self, session):
        """generate_summaries() processes all (channel, user) pairs in one call."""
        _make_message(session, "ch1", "u1", "Alice", "First message", 1)
        _make_message(session, "ch1", "u2", "Bob", "Second message", 2)
        _make_message(session, "ch2", "u1", "Alice", "Third message", 3)

        summaries_generated = []

        async def mock_llm(prompt: str) -> str:
            summary = f"summary for prompt"
            summaries_generated.append(prompt)
            return summary

        await generate_summaries(session, mock_llm)

        # Three unique (channel, user) pairs: (ch1, u1), (ch1, u2), (ch2, u1)
        all_summaries = session.exec(select(UserChannelSummary)).all()
        assert len(all_summaries) == 3
        assert len(summaries_generated) == 3

    @pytest.mark.asyncio
    async def test_all_pairs_fail_does_not_raise(self, session):
        """generate_summaries() completes without raising even when all pairs fail."""
        _make_message(session, "ch1", "u1", "Alice", "Message", 1)

        async def always_fail(prompt: str) -> str:
            raise RuntimeError("always fails")

        # Should not propagate the exception
        await generate_summaries(session, always_fail)

        summaries = session.exec(select(UserChannelSummary)).all()
        assert len(summaries) == 0
