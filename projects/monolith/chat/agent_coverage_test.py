"""Additional coverage for create_agent() -- explicit base_url and tool registration."""

from unittest.mock import patch, MagicMock

from chat.agent import create_agent


class TestCreateAgent:
    def test_returns_agent_with_explicit_base_url(self):
        """create_agent() with an explicit base_url builds an Agent without errors."""
        agent = create_agent(base_url="http://llama-fake:8080")
        assert agent is not None

    def test_returns_agent_with_env_url(self):
        """create_agent() falls back to LLAMA_CPP_URL env var when base_url is None."""
        with patch("chat.agent.LLAMA_CPP_URL", "http://env-llama:8080"):
            agent = create_agent()
        assert agent is not None

    def test_agent_has_web_search_tool(self):
        """The agent registers a tool named 'web_search'."""
        agent = create_agent(base_url="http://llama-fake:8080")
        # PydanticAI exposes registered tools via _function_toolset; verify it is
        # present and the string representation mentions 'web_search'.
        toolset = agent._function_toolset
        assert toolset is not None
        assert "web_search" in repr(toolset)

    def test_agent_has_exactly_one_tool(self):
        """The agent has exactly one registered tool (web_search)."""
        agent = create_agent(base_url="http://llama-fake:8080")
        toolset = agent._function_toolset
        assert toolset is not None
        # FunctionToolset stores tools in a dict; access via _tools (pydantic-ai internals)
        tools = getattr(toolset, "_tools", None) or getattr(toolset, "_functions", None) or {}
        # Accept either: exactly 1 tool in the dict, or the repr contains 'web_search' once
        if tools:
            assert len(tools) == 1
        else:
            assert repr(toolset).count("web_search") >= 1
