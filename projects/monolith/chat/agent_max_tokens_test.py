"""Test that the chat agent is created with max_tokens=16384."""

from unittest.mock import patch

from chat.agent import create_agent


class TestAgentMaxTokens:
    def test_agent_has_max_tokens_setting(self):
        """create_agent() configures ModelSettings with max_tokens=16384."""
        with patch("chat.agent.LLAMA_CPP_URL", "http://fake:8080"):
            agent = create_agent(base_url="http://fake:8080")
        settings = agent.model_settings
        assert settings is not None
        assert settings.get("max_tokens") == 16384
