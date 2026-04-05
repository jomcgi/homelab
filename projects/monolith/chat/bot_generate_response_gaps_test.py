"""Tests for uncovered branches in _generate_response() and _summarize_thinking().

Covers the following gaps identified after commits 5ec07cbc..367865d1:

1. _summarize_thinking(): when the LLM's own summary exceeds DISCORD_MESSAGE_LIMIT,
   the secondary truncation path (line 81-82 in bot.py) kicks in and returns
   summary[:THINKING_TRUNCATE_AT] + '... (truncated)'.

2. on_message(): after a successful reply the bot stores its own response; the
   second save_message() call must receive is_bot=True, the correct content, and
   the sent message id.

3. _generate_response() thinking-only retry with image attachments: when the first
   agent call returns empty output (thinking only) AND image parts are present, the
   nudge retry prompt must be a plain string (not a multimodal list).

4. _generate_response() mixed attachments: one attachment with valid bytes and one
   with data=None produces exactly one BinaryContent while including both image
   descriptions in the text prompt.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart

from chat.bot import (
    DISCORD_MESSAGE_LIMIT,
    THINKING_TRUNCATE_AT,
    ChatBot,
    _summarize_thinking,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class _AsyncCtxManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _async_cm():
    return _AsyncCtxManager()


def _make_message(
    content: str = "hello",
    channel_id: int = 99,
    msg_id: int = 1,
    mentions: list | None = None,
) -> MagicMock:
    msg = MagicMock()
    msg.id = msg_id
    msg.content = content
    msg.author.bot = False
    msg.author.id = 42
    msg.author.display_name = "TestUser"
    msg.channel.id = channel_id
    msg.channel.typing = MagicMock(return_value=_async_cm())
    msg.mentions = mentions if mentions is not None else []
    msg.reference = None
    msg.attachments = []
    msg.reply = AsyncMock(return_value=MagicMock(id=100))
    return msg


def _make_bot() -> ChatBot:
    """Build a ChatBot with mocked internals."""
    with (
        patch("chat.bot.EmbeddingClient") as mock_ec,
        patch("chat.bot.VisionClient"),
        patch("chat.bot.create_agent") as mock_ca,
    ):
        mock_ec.return_value = AsyncMock()
        mock_ca.return_value = MagicMock()
        bot = ChatBot()
    bot._connection = MagicMock()
    bot._connection.user = MagicMock()
    bot._connection.user.id = 999
    bot._connection.user.display_name = "BotUser"
    return bot


def _make_agent_result(output: str, thinking: str | None = None) -> MagicMock:
    """Build a mock agent result with optional ThinkingPart."""
    parts = []
    if thinking is not None:
        parts.append(ThinkingPart(content=thinking))
    parts.append(TextPart(content=output))
    response = ModelResponse(parts=parts)
    result = MagicMock()
    result.output = output
    result.new_messages.return_value = [response]
    return result


def _setup_store_mock() -> MagicMock:
    """Return a store mock wired with empty recent/attachments."""
    store = MagicMock()
    store.get_recent = MagicMock(return_value=[])
    store.get_attachments = MagicMock(return_value={})
    store.save_message = AsyncMock()
    return store


# ---------------------------------------------------------------------------
# Gap 1: _summarize_thinking — LLM summary itself exceeds DISCORD_MESSAGE_LIMIT
# ---------------------------------------------------------------------------


class TestSummarizeThinkingOversizedSummary:
    @pytest.mark.asyncio
    async def test_oversized_llm_summary_is_truncated(self):
        """When the LLM returns a summary longer than DISCORD_MESSAGE_LIMIT,
        _summarize_thinking truncates it to THINKING_TRUNCATE_AT chars and appends
        '... (truncated)'."""
        long_input = "x" * (DISCORD_MESSAGE_LIMIT + 1)
        # The LLM returns a summary that is itself too long
        oversized_summary = "y" * (DISCORD_MESSAGE_LIMIT + 1)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": oversized_summary}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            result = await _summarize_thinking(long_input, base_url="http://fake:8080")

        # Must fit within Discord's limit
        assert len(result) <= DISCORD_MESSAGE_LIMIT
        # Must end with the truncation marker
        assert result.endswith("... (truncated)")
        # Content must be the start of the oversized summary
        assert result == oversized_summary[:THINKING_TRUNCATE_AT] + "... (truncated)"

    @pytest.mark.asyncio
    async def test_oversized_summary_prefix_length_matches_truncate_constant(self):
        """The truncated prefix is exactly THINKING_TRUNCATE_AT characters long."""
        long_input = "a" * (DISCORD_MESSAGE_LIMIT + 100)
        oversized_summary = "b" * (DISCORD_MESSAGE_LIMIT + 500)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": oversized_summary}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            result = await _summarize_thinking(long_input, base_url="http://fake:8080")

        suffix = "... (truncated)"
        prefix_len = len(result) - len(suffix)
        assert prefix_len == THINKING_TRUNCATE_AT

    @pytest.mark.asyncio
    async def test_summary_at_exactly_limit_is_not_truncated(self):
        """A summary exactly at DISCORD_MESSAGE_LIMIT is returned verbatim."""
        long_input = "x" * (DISCORD_MESSAGE_LIMIT + 1)
        exact_summary = "z" * DISCORD_MESSAGE_LIMIT  # exactly at the limit

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": exact_summary}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("chat.bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            result = await _summarize_thinking(long_input, base_url="http://fake:8080")

        # Exactly at limit — must be returned as-is (not truncated)
        assert result == exact_summary
        assert not result.endswith("... (truncated)")


# ---------------------------------------------------------------------------
# Gap 2: on_message — bot response stored with correct arguments
# ---------------------------------------------------------------------------


class TestOnMessageBotResponseStorage:
    @pytest.mark.asyncio
    async def test_bot_response_saved_with_is_bot_true(self):
        """After a successful reply, on_message saves the bot response with is_bot=True."""
        bot = _make_bot()
        bot_user = bot.user

        sent_msg = MagicMock()
        sent_msg.id = 888
        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reply = AsyncMock(return_value=sent_msg)

        mock_store = _setup_store_mock()
        mock_result = _make_agent_result("My answer!")
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        # save_message is called twice: once for user message, once for bot response
        assert mock_store.save_message.call_count == 2
        # The second call is the bot's own response
        bot_save_kwargs = mock_store.save_message.call_args_list[1][1]
        assert bot_save_kwargs["is_bot"] is True

    @pytest.mark.asyncio
    async def test_bot_response_saved_with_correct_content(self):
        """The bot response stored in the second save_message call matches the reply text."""
        bot = _make_bot()
        bot_user = bot.user

        sent_msg = MagicMock()
        sent_msg.id = 777
        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reply = AsyncMock(return_value=sent_msg)

        mock_store = _setup_store_mock()
        mock_result = _make_agent_result("Specific response text")
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        bot_save_kwargs = mock_store.save_message.call_args_list[1][1]
        assert bot_save_kwargs["content"] == "Specific response text"

    @pytest.mark.asyncio
    async def test_bot_response_saved_with_sent_message_id(self):
        """The discord_message_id in the second save_message call is the sent message's id."""
        bot = _make_bot()
        bot_user = bot.user

        sent_msg = MagicMock()
        sent_msg.id = 12345
        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reply = AsyncMock(return_value=sent_msg)

        mock_store = _setup_store_mock()
        mock_result = _make_agent_result("A response")
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        bot_save_kwargs = mock_store.save_message.call_args_list[1][1]
        assert bot_save_kwargs["discord_message_id"] == str(sent_msg.id)

    @pytest.mark.asyncio
    async def test_bot_response_saved_with_bot_user_id(self):
        """The user_id in the second save_message call is the bot's own user id."""
        bot = _make_bot()
        bot._connection.user.id = 999
        bot_user = bot.user

        sent_msg = MagicMock()
        sent_msg.id = 100
        message = _make_message(content="Hey bot!", mentions=[bot_user])
        message.reply = AsyncMock(return_value=sent_msg)

        mock_store = _setup_store_mock()
        mock_result = _make_agent_result("Response!")
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot.on_message(message)

        bot_save_kwargs = mock_store.save_message.call_args_list[1][1]
        assert bot_save_kwargs["user_id"] == str(bot._connection.user.id)


# ---------------------------------------------------------------------------
# Gap 3: _generate_response — thinking-only retry with image attachments
# ---------------------------------------------------------------------------


class TestThinkingRetryWithImageAttachments:
    @pytest.mark.asyncio
    async def test_nudge_prompt_is_plain_string_even_when_images_present(self):
        """When the first call returns only thinking (no output) AND images are
        attached, the retry nudge prompt is a plain string — not a multimodal list.

        This ensures the retry path does not silently fail due to type mismatch.
        """
        bot = _make_bot()
        msg = _make_message(content="What is this image?")
        mock_store = _setup_store_mock()

        attachments = [
            {
                "data": b"\x89PNG\r\n\x1a\n",
                "content_type": "image/png",
                "filename": "meme.png",
                "description": "A cat meme",
            }
        ]

        # First call: empty output with thinking (thinking-only path)
        # Second call: proper response
        thinking_only = _make_agent_result("", thinking="some reasoning here")
        proper_response = _make_agent_result("Here is my answer about the image!")
        bot.agent.run = AsyncMock(side_effect=[thinking_only, proper_response])

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot.search_web", new_callable=AsyncMock, return_value="results"
            ),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = await bot._generate_response(msg, current_attachments=attachments)

        assert bot.agent.run.call_count == 2
        # First call must be multimodal (list)
        first_prompt = bot.agent.run.call_args_list[0][0][0]
        assert isinstance(first_prompt, list), (
            "First call with image data should use a multimodal list prompt"
        )
        # Second (nudge) call must be a plain string
        second_prompt = bot.agent.run.call_args_list[1][0][0]
        assert isinstance(second_prompt, str), (
            "Nudge retry should send a plain string prompt"
        )
        # Result must be the second call's output
        assert result[0] == "Here is my answer about the image!"

    @pytest.mark.asyncio
    async def test_nudge_prompt_contains_original_user_prompt_text(self):
        """The nudge retry prompt contains the original user prompt text and the
        'Please respond to the user directly' instruction."""
        bot = _make_bot()
        msg = _make_message(content="Tell me about this photo")
        mock_store = _setup_store_mock()

        attachments = [
            {
                "data": b"\xff\xd8\xff",
                "content_type": "image/jpeg",
                "filename": "photo.jpg",
                "description": "A landscape photo",
            }
        ]

        thinking_only = _make_agent_result("", thinking="pondering")
        proper_response = _make_agent_result("Nice landscape!")
        bot.agent.run = AsyncMock(side_effect=[thinking_only, proper_response])

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.search_web", new_callable=AsyncMock, return_value="ok"),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg, current_attachments=attachments)

        nudge_prompt = bot.agent.run.call_args_list[1][0][0]
        assert isinstance(nudge_prompt, str)
        assert "Tell me about this photo" in nudge_prompt
        assert "respond to the user" in nudge_prompt.lower()


# ---------------------------------------------------------------------------
# Gap 4: _generate_response — mixed attachments (one valid, one failed/None)
# ---------------------------------------------------------------------------


class TestMixedAttachments:
    @pytest.mark.asyncio
    async def test_mixed_attachments_produce_one_binary_content(self):
        """When one attachment has valid bytes and another has data=None,
        only one BinaryContent is forwarded to the agent."""
        bot = _make_bot()
        msg = _make_message(content="Here are two images")
        mock_store = _setup_store_mock()

        attachments = [
            {
                "data": b"\x89PNG\r\n\x1a\n",
                "content_type": "image/png",
                "filename": "valid.png",
                "description": "A valid image",
            },
            {
                "data": None,
                "content_type": "image/jpeg",
                "filename": "broken.jpg",
                "description": "(image could not be processed)",
            },
        ]

        mock_result = _make_agent_result("I see one image and one broken attachment.")
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.search_web", new_callable=AsyncMock, return_value="ok"),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg, current_attachments=attachments)

        prompt_arg = bot.agent.run.call_args[0][0]
        # Prompt is a list because there is at least one valid image
        assert isinstance(prompt_arg, list)
        binary_parts = [p for p in prompt_arg if isinstance(p, BinaryContent)]
        # Only the attachment with valid data produces a BinaryContent
        assert len(binary_parts) == 1
        assert binary_parts[0].data == b"\x89PNG\r\n\x1a\n"
        assert binary_parts[0].media_type == "image/png"

    @pytest.mark.asyncio
    async def test_both_attachment_descriptions_appear_in_text_prompt(self):
        """Both attachment descriptions (valid and failed) appear in the text portion
        of the prompt so the model is aware of both."""
        bot = _make_bot()
        msg = _make_message(content="Check these")
        mock_store = _setup_store_mock()

        attachments = [
            {
                "data": b"\x89PNG",
                "content_type": "image/png",
                "filename": "good.png",
                "description": "A sunny day",
            },
            {
                "data": None,
                "content_type": "image/jpeg",
                "filename": "bad.jpg",
                "description": "(image could not be processed)",
            },
        ]

        mock_result = _make_agent_result("Understood!")
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch(
                "chat.bot.search_web",
                new_callable=AsyncMock,
                return_value="search results",
            ),
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            await bot._generate_response(msg, current_attachments=attachments)

        prompt_arg = bot.agent.run.call_args[0][0]
        text_parts = [p for p in prompt_arg if isinstance(p, str)]
        combined_text = " ".join(text_parts)
        assert "good.png" in combined_text
        assert "A sunny day" in combined_text
        assert "bad.jpg" in combined_text
        assert "(image could not be processed)" in combined_text

    @pytest.mark.asyncio
    async def test_auto_search_uses_only_valid_descriptions(self):
        """Auto-search skips the '(image could not be processed)' sentinel and uses
        only the valid image description."""
        bot = _make_bot()
        msg = _make_message(content="What is this?")
        mock_store = _setup_store_mock()

        attachments = [
            {
                "data": b"\x89PNG",
                "content_type": "image/png",
                "filename": "good.png",
                "description": "Breaking news headline",
            },
            {
                "data": None,
                "content_type": "image/jpeg",
                "filename": "broken.jpg",
                "description": "(image could not be processed)",
            },
        ]

        mock_result = _make_agent_result("Here's the news!")
        bot.agent.run = AsyncMock(return_value=mock_result)

        with (
            patch("chat.bot.get_engine"),
            patch("chat.bot.Session") as mock_session_cls,
            patch("chat.bot.MessageStore", return_value=mock_store),
            patch("chat.bot.search_web", new_callable=AsyncMock) as mock_search,
        ):
            mock_session_cls.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_search.return_value = "search results"
            await bot._generate_response(msg, current_attachments=attachments)

        # search_web must have been called (the valid description passes the filter)
        mock_search.assert_called_once()
        search_query = mock_search.call_args[0][0]
        # Only the valid description contributes to the search query
        assert "Breaking news headline" in search_query
        # The failure sentinel must NOT appear in the search query
        assert "(image could not be processed)" not in search_query
