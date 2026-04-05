"""Tests for tool registration in the PydanticAI chat agent."""

import pytest

from chat.agent import create_agent


class TestAgentToolRegistration:
    def test_search_history_tool_registered(self):
        """create_agent() registers 'search_history' as a callable tool."""
        agent = create_agent(base_url="http://fake:8080")
        tool_names = set(agent._function_toolset.tools.keys())
        assert "search_history" in tool_names

    def test_get_user_summary_tool_registered(self):
        """create_agent() registers 'get_user_summary' as a callable tool."""
        agent = create_agent(base_url="http://fake:8080")
        tool_names = set(agent._function_toolset.tools.keys())
        assert "get_user_summary" in tool_names

    def test_web_search_tool_registered(self):
        """create_agent() registers 'web_search' as a callable tool."""
        agent = create_agent(base_url="http://fake:8080")
        tool_names = set(agent._function_toolset.tools.keys())
        assert "web_search" in tool_names

    def test_all_three_tools_registered(self):
        """create_agent() registers exactly web_search, search_history, and get_user_summary."""
        agent = create_agent(base_url="http://fake:8080")
        tool_names = set(agent._function_toolset.tools.keys())
        expected_tools = {"web_search", "search_history", "get_user_summary"}
        assert expected_tools.issubset(tool_names)


class TestSignpostedDecorator:
    def test_attaches_signpost_attribute(self):
        """signposted decorator attaches .signpost to the function."""
        from chat.agent import signposted

        @signposted("test guidance")
        def dummy():
            pass

        assert dummy.signpost == "test guidance"

    def test_preserves_function_name(self):
        """signposted decorator preserves the original function name."""
        from chat.agent import signposted

        @signposted("test")
        def my_func():
            pass

        assert my_func.__name__ == "my_func"
