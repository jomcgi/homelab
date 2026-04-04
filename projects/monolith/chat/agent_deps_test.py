"""Tests for ChatDeps and agent dependency injection."""

from unittest.mock import AsyncMock, MagicMock

from chat.agent import ChatDeps, create_agent


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
    def test_agent_has_search_history_tool(self):
        """create_agent registers a search_history tool."""
        agent = create_agent(base_url="http://fake:8080")
        tool_names = [t.name for t in agent._function_toolset.values()]
        assert "search_history" in tool_names

    def test_agent_has_get_user_summary_tool(self):
        """create_agent registers a get_user_summary tool."""
        agent = create_agent(base_url="http://fake:8080")
        tool_names = [t.name for t in agent._function_toolset.values()]
        assert "get_user_summary" in tool_names

    def test_system_prompt_references_search_history(self):
        """System prompt tells the agent about search_history."""
        from chat.agent import build_system_prompt

        prompt = build_system_prompt()
        assert "search_history" in prompt

    def test_system_prompt_references_get_user_summary(self):
        """System prompt tells the agent about get_user_summary."""
        from chat.agent import build_system_prompt

        prompt = build_system_prompt()
        assert "get_user_summary" in prompt
