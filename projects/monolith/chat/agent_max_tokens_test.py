"""Test that the chat agent does not set an explicit max_tokens."""

from unittest.mock import patch

from chat.agent import create_agent


class TestAgentMaxTokens:
    def test_agent_does_not_set_max_tokens(self):
        """create_agent() should not hardcode max_tokens so vLLM uses remaining context."""
        with patch("chat.agent.LLAMA_CPP_URL", "http://fake:8080"):
            agent = create_agent(base_url="http://fake:8080")
        settings = agent.model_settings
        assert settings is not None
        assert settings.get("max_tokens") is None
