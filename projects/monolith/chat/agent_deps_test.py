"""Tests for ChatDeps and agent dependency injection."""

from unittest.mock import AsyncMock, MagicMock

from chat.agent import ChatDeps, build_system_prompt, create_agent


class TestChatDeps:
    def test_creates_deps_instance(self):
        """ChatDeps holds channel_id, store, and embed_client."""
        deps = ChatDeps(
            channel_id="ch1",
            store=MagicMock(),
            embed_client=AsyncMock(),
        )
        assert deps.channel_id == "ch1"


class TestCreateAgentWithDeps:
    def test_agent_creates_successfully(self):
        """create_agent returns an Agent parameterized with ChatDeps."""
        agent = create_agent(base_url="http://fake:8080")
        assert agent is not None

    def test_system_prompt_references_search_history(self):
        """System prompt tells the agent about search_history."""
        prompt = build_system_prompt()
        assert "search_history" in prompt

    def test_system_prompt_references_get_user_summary(self):
        """System prompt tells the agent about get_user_summary."""
        prompt = build_system_prompt()
        assert "get_user_summary" in prompt

    def test_system_prompt_references_web_search(self):
        """System prompt tells the agent about web_search."""
        prompt = build_system_prompt()
        assert "web_search" in prompt
