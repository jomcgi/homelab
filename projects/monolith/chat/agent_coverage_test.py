"""Additional coverage for create_agent() -- explicit base_url and tool registration."""

from unittest.mock import patch

from pydantic_ai import Agent

from chat.agent import build_system_prompt, create_agent


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

    def test_returns_pydantic_ai_agent_instance(self):
        """create_agent() returns a proper pydantic_ai Agent instance."""
        agent = create_agent(base_url="http://llama-fake:8080")
        assert isinstance(agent, Agent)

    def test_system_prompt_references_web_search(self):
        """The system prompt instructs the model about the web_search tool."""
        prompt = build_system_prompt()
        assert "web_search" in prompt
        assert "Discord" in prompt
