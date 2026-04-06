"""Focused tests for ThinkingView.show_thinking() Discord button callback.

Covers the button callback handler that sends the AI reasoning text as an
ephemeral (private) message to the user who clicks the button.

These tests complement the basic ephemeral-send test in bot_thinking_test.py
by exercising the method's contract more thoroughly:

- Direct invocation via ``view.show_thinking(interaction, button)`` (full
  method signature including the ``button`` parameter).
- Varied thinking content: empty, multiline, Unicode, Discord markdown.
- Side-effect isolation: only ``response.send_message`` is called; no other
  Discord response primitives (``defer``, ``edit_message``, etc.) are
  invoked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

import discord

from chat.bot import ThinkingView


def _make_interaction() -> AsyncMock:
    """Return a fully mocked Discord Interaction whose response supports send_message."""
    interaction = AsyncMock()
    interaction.response = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    return interaction


def _make_button() -> MagicMock:
    """Return a minimal mock of discord.ui.Button."""
    return MagicMock(spec=discord.ui.Button)


class TestShowThinkingCallback:
    """Unit tests for ThinkingView.show_thinking() — the button callback."""

    @pytest.mark.asyncio
    async def test_sends_ephemeral_with_thinking_content(self):
        """Clicking the button sends the stored thinking text as an ephemeral reply."""
        view = ThinkingView("AI reasoning text")
        interaction = _make_interaction()
        button = _make_button()

        await view.show_thinking(interaction, button)

        interaction.response.send_message.assert_called_once_with(
            "AI reasoning text", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_ephemeral_flag_is_always_true(self):
        """The ephemeral=True keyword argument must always be present."""
        view = ThinkingView("some reasoning")
        interaction = _make_interaction()
        button = _make_button()

        await view.show_thinking(interaction, button)

        _, kwargs = interaction.response.send_message.call_args
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_exact_thinking_text_is_sent(self):
        """The positional argument to send_message is exactly the stored thinking text."""
        thinking = "Step 1: consider X\nStep 2: conclude Y"
        view = ThinkingView(thinking)
        interaction = _make_interaction()
        button = _make_button()

        await view.show_thinking(interaction, button)

        args, _ = interaction.response.send_message.call_args
        assert args[0] == thinking

    @pytest.mark.asyncio
    async def test_empty_thinking_text(self):
        """An empty thinking string is forwarded unchanged (no special-casing)."""
        view = ThinkingView("")
        interaction = _make_interaction()
        button = _make_button()

        await view.show_thinking(interaction, button)

        interaction.response.send_message.assert_called_once_with("", ephemeral=True)

    @pytest.mark.asyncio
    async def test_multiline_thinking_text(self):
        """Multiline reasoning is forwarded verbatim."""
        multiline = "First thought.\n\nSecond thought.\n\nConclusion."
        view = ThinkingView(multiline)
        interaction = _make_interaction()
        button = _make_button()

        await view.show_thinking(interaction, button)

        interaction.response.send_message.assert_called_once_with(
            multiline, ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_unicode_and_emoji_thinking(self):
        """Unicode characters and emojis in thinking text pass through unmodified."""
        unicode_thinking = "思考: 🤔 résumé — naïve approach → 42"
        view = ThinkingView(unicode_thinking)
        interaction = _make_interaction()
        button = _make_button()

        await view.show_thinking(interaction, button)

        interaction.response.send_message.assert_called_once_with(
            unicode_thinking, ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_discord_markdown_preserved(self):
        """Discord markdown formatting characters in thinking are not escaped."""
        markdown_thinking = "**bold** _italic_ `code` ~~strike~~ > blockquote"
        view = ThinkingView(markdown_thinking)
        interaction = _make_interaction()
        button = _make_button()

        await view.show_thinking(interaction, button)

        interaction.response.send_message.assert_called_once_with(
            markdown_thinking, ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_only_send_message_is_called(self):
        """No other response methods (defer, edit_message) are invoked."""
        view = ThinkingView("reasoning")
        interaction = _make_interaction()
        button = _make_button()

        await view.show_thinking(interaction, button)

        interaction.response.defer.assert_not_called()
        interaction.response.edit_message.assert_not_called()
        interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_called_exactly_once(self):
        """send_message is called exactly once — no duplicate responses."""
        view = ThinkingView("reasoning")
        interaction = _make_interaction()
        button = _make_button()

        await view.show_thinking(interaction, button)

        assert interaction.response.send_message.call_count == 1

    @pytest.mark.asyncio
    async def test_different_thinking_texts_produce_different_messages(self):
        """Two separate views with different thinking texts send different content."""
        view_a = ThinkingView("reasoning A")
        view_b = ThinkingView("reasoning B")
        interaction_a = _make_interaction()
        interaction_b = _make_interaction()
        button = _make_button()

        await view_a.show_thinking(interaction_a, button)
        await view_b.show_thinking(interaction_b, button)

        args_a, _ = interaction_a.response.send_message.call_args
        args_b, _ = interaction_b.response.send_message.call_args
        assert args_a[0] == "reasoning A"
        assert args_b[0] == "reasoning B"

    @pytest.mark.asyncio
    async def test_button_argument_is_not_used_in_response(self):
        """The button parameter does not influence the message sent to the user."""
        view = ThinkingView("consistent thinking")
        interaction = _make_interaction()

        # Two different button mocks — message should be identical
        button_1 = MagicMock(spec=discord.ui.Button, label="Show thinking")
        button_2 = MagicMock(spec=discord.ui.Button, label="Other label")

        await view.show_thinking(interaction, button_1)
        first_call_args = interaction.response.send_message.call_args

        interaction.response.send_message.reset_mock()
        await view.show_thinking(interaction, button_2)
        second_call_args = interaction.response.send_message.call_args

        assert first_call_args == second_call_args
