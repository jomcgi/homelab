"""Tests for Discord bot integration."""

from unittest.mock import MagicMock

from chat.bot import should_respond


class TestShouldRespond:
    def test_responds_to_mention(self):
        """Bot responds when mentioned."""
        message = MagicMock()
        message.author.bot = False
        message.content = "Hello"
        bot_user = MagicMock()
        bot_user.id = 12345
        message.mentions = [bot_user]
        assert should_respond(message, bot_user) is True

    def test_ignores_bot_messages(self):
        """Bot does not respond to other bots."""
        message = MagicMock()
        message.author.bot = True
        message.content = "Hello"
        bot_user = MagicMock()
        message.mentions = []
        assert should_respond(message, bot_user) is False

    def test_ignores_unmentioned_messages(self):
        """Bot does not respond to messages that don't mention it."""
        message = MagicMock()
        message.author.bot = False
        message.content = "Hello everyone"
        bot_user = MagicMock()
        bot_user.id = 12345
        message.mentions = []
        message.reference = None
        assert should_respond(message, bot_user) is False

    def test_responds_to_reply(self):
        """Bot responds when a message is a reply to a bot message."""
        message = MagicMock()
        message.author.bot = False
        message.content = "Thanks"
        bot_user = MagicMock()
        bot_user.id = 12345
        message.mentions = []
        message.reference = MagicMock()
        message.reference.resolved = MagicMock()
        message.reference.resolved.author.id = 12345
        assert should_respond(message, bot_user) is True
