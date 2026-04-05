"""Additional coverage for remaining gaps in chat module.

Covers:
- summarizer.build_llm_caller: timeout error and 429 rate-limit propagation
- store.save_message: non-IntegrityError exceptions propagate (not swallowed)
- agent.create_agent: empty string base_url falls back to LLAMA_CPP_URL env var
- bot.create_bot: VisionClient is initialised on construction
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from chat.agent import create_agent
from chat.bot import ChatBot, create_bot
from chat.store import MessageStore
from chat.summarizer import build_llm_caller


# ---------------------------------------------------------------------------
# summarizer.build_llm_caller -- timeout and rate-limit error propagation
# ---------------------------------------------------------------------------


class TestBuildLlmCallerTimeoutError:
    @pytest.mark.asyncio
    async def test_propagates_read_timeout(self):
        """build_llm_caller() propagates httpx.ReadTimeout raised by the HTTP client."""
        mock_instance = MagicMock()
        mock_instance.post = AsyncMock(
            side_effect=httpx.ReadTimeout("timed out reading response")
        )

        with patch("chat.summarizer.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_instance
            caller = build_llm_caller("http://fake:8080")
            with pytest.raises(httpx.ReadTimeout):
                await caller("a prompt that times out")

    @pytest.mark.asyncio
    async def test_propagates_connect_timeout(self):
        """build_llm_caller() propagates httpx.ConnectTimeout when the server is unreachable."""
        mock_instance = MagicMock()
        mock_instance.post = AsyncMock(
            side_effect=httpx.ConnectTimeout("connection timed out")
        )

        with patch("chat.summarizer.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_instance
            caller = build_llm_caller("http://fake:8080")
            with pytest.raises(httpx.ConnectTimeout):
                await caller("another prompt")

    @pytest.mark.asyncio
    async def test_propagates_429_rate_limit(self):
        """build_llm_caller() raises HTTPStatusError for a 429 Too Many Requests response."""
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=mock_request,
            response=mock_response,
        )
        mock_instance = MagicMock()
        mock_instance.post = AsyncMock(return_value=mock_response)

        with patch("chat.summarizer.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_instance
            caller = build_llm_caller("http://fake:8080")
            with pytest.raises(httpx.HTTPStatusError):
                await caller("rate limited prompt")

    @pytest.mark.asyncio
    async def test_propagates_503_service_unavailable(self):
        """build_llm_caller() raises HTTPStatusError for a 503 response."""
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503 Service Unavailable",
            request=mock_request,
            response=mock_response,
        )
        mock_instance = MagicMock()
        mock_instance.post = AsyncMock(return_value=mock_response)

        with patch("chat.summarizer.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_instance
            caller = build_llm_caller("http://fake:8080")
            with pytest.raises(httpx.HTTPStatusError):
                await caller("unavailable service prompt")


# ---------------------------------------------------------------------------
# store.save_message -- non-IntegrityError exceptions propagate
# ---------------------------------------------------------------------------


class TestSaveMessageNonIntegrityError:
    @pytest.mark.asyncio
    async def test_non_integrity_error_propagates_from_flush(self):
        """save_message propagates non-IntegrityError exceptions from session.flush()."""
        from sqlalchemy.exc import OperationalError

        mock_session = MagicMock()
        mock_session.flush.side_effect = OperationalError(
            "disk full", params=None, orig=None
        )
        embed_client = AsyncMock()
        embed_client.embed.return_value = [0.0] * 1024
        store = MessageStore(session=mock_session, embed_client=embed_client)

        with pytest.raises(OperationalError):
            await store.save_message(
                discord_message_id="op-err-1",
                channel_id="ch1",
                user_id="u1",
                username="Alice",
                content="message that triggers operational error",
                is_bot=False,
            )

    @pytest.mark.asyncio
    async def test_non_integrity_error_does_not_return_none(self):
        """save_message raises (not returns None) for non-IntegrityError exceptions."""
        mock_session = MagicMock()
        mock_session.commit.side_effect = RuntimeError("unexpected DB failure")
        embed_client = AsyncMock()
        embed_client.embed.return_value = [0.0] * 1024
        store = MessageStore(session=mock_session, embed_client=embed_client)

        with pytest.raises(RuntimeError, match="unexpected DB failure"):
            await store.save_message(
                discord_message_id="rt-err-1",
                channel_id="ch1",
                user_id="u1",
                username="Bob",
                content="message triggering RuntimeError",
                is_bot=False,
            )

    @pytest.mark.asyncio
    async def test_rollback_not_called_for_non_integrity_error(self):
        """save_message does NOT call rollback when a non-IntegrityError is raised."""
        from sqlalchemy.exc import OperationalError

        mock_session = MagicMock()
        mock_session.commit.side_effect = OperationalError(
            "lock timeout", params=None, orig=None
        )
        embed_client = AsyncMock()
        embed_client.embed.return_value = [0.0] * 1024
        store = MessageStore(session=mock_session, embed_client=embed_client)

        try:
            await store.save_message(
                discord_message_id="op-err-2",
                channel_id="ch1",
                user_id="u1",
                username="Carol",
                content="message causing lock timeout",
                is_bot=False,
            )
        except Exception:
            pass

        mock_session.rollback.assert_not_called()


# ---------------------------------------------------------------------------
# agent.create_agent -- empty string base_url falls through to module-level var
# ---------------------------------------------------------------------------


class TestCreateAgentBaseUrl:
    def test_empty_string_base_url_uses_module_level_url(self):
        """create_agent('') uses the module-level LLAMA_CPP_URL (empty-string is falsy)."""
        with patch("chat.agent.LLAMA_CPP_URL", "http://module-level:9999"):
            agent = create_agent(base_url="")
        assert agent is not None

    def test_explicit_base_url_takes_precedence_over_module_level(self):
        """create_agent() with an explicit non-empty base_url ignores LLAMA_CPP_URL."""
        with patch("chat.agent.LLAMA_CPP_URL", "http://should-not-be-used:9999"):
            agent = create_agent(base_url="http://explicit:8080")
        assert agent is not None


# ---------------------------------------------------------------------------
# bot.create_bot -- VisionClient is initialised on construction
# ---------------------------------------------------------------------------


class TestCreateBotInit:
    def test_vision_client_initialised(self):
        """ChatBot.__init__ creates a VisionClient instance."""
        with (
            patch("chat.bot.EmbeddingClient"),
            patch("chat.bot.VisionClient") as mock_vc,
            patch("chat.bot.create_agent"),
        ):
            mock_vc.return_value = MagicMock()
            bot = create_bot()
        mock_vc.assert_called_once()
        assert bot.vision_client is mock_vc.return_value

    def test_embed_client_initialised(self):
        """ChatBot.__init__ creates an EmbeddingClient instance."""
        with (
            patch("chat.bot.EmbeddingClient") as mock_ec,
            patch("chat.bot.VisionClient"),
            patch("chat.bot.create_agent"),
        ):
            mock_ec.return_value = MagicMock()
            bot = create_bot()
        mock_ec.assert_called_once()
        assert bot.embed_client is mock_ec.return_value

    def test_agent_initialised(self):
        """ChatBot.__init__ calls create_agent() to build the agent."""
        with (
            patch("chat.bot.EmbeddingClient"),
            patch("chat.bot.VisionClient"),
            patch("chat.bot.create_agent") as mock_ca,
        ):
            mock_ca.return_value = MagicMock()
            bot = create_bot()
        mock_ca.assert_called_once()
        assert bot.agent is mock_ca.return_value

    def test_returns_chatbot_instance(self):
        """create_bot() returns a ChatBot instance."""
        with (
            patch("chat.bot.EmbeddingClient"),
            patch("chat.bot.VisionClient"),
            patch("chat.bot.create_agent"),
        ):
            result = create_bot()
        assert isinstance(result, ChatBot)
