"""Behavioral tests for inject_signposts() in agent.py.

inject_signposts() is the prepare_tools callback that rewrites each tool's
ToolDefinition description to append 'USE WHEN: <signpost>' at runtime.
The enriched descriptions are injected into the chat template's <tools>
block by vLLM, so no separate system prompt is needed.
"""

from unittest.mock import MagicMock

import pytest
from pydantic_ai import ToolDefinition

from chat.agent import create_agent


# ---------------------------------------------------------------------------
# inject_signposts() behavioral tests
# ---------------------------------------------------------------------------


class TestInjectSignpostsBehavior:
    @pytest.mark.asyncio
    async def test_web_search_description_gets_use_when_suffix(self):
        """inject_signposts() appends 'USE WHEN: ...' to web_search description."""
        agent = create_agent(base_url="http://fake:8080")

        td = ToolDefinition(
            name="web_search",
            description="Search the web for current information.",
            parameters_json_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        )

        ctx = MagicMock()
        updated = await agent._prepare_tools(ctx, [td])

        assert len(updated) == 1
        assert "USE WHEN:" in updated[0].description
        assert updated[0].name == "web_search"

    @pytest.mark.asyncio
    async def test_search_history_description_gets_use_when_suffix(self):
        """inject_signposts() appends 'USE WHEN: ...' to search_history description."""
        agent = create_agent(base_url="http://fake:8080")

        td = ToolDefinition(
            name="search_history",
            description="Search older messages in this channel by topic.",
            parameters_json_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        )

        ctx = MagicMock()
        updated = await agent._prepare_tools(ctx, [td])

        assert len(updated) == 1
        assert "USE WHEN:" in updated[0].description
        assert updated[0].name == "search_history"

    @pytest.mark.asyncio
    async def test_get_user_summary_description_gets_use_when_suffix(self):
        """inject_signposts() appends 'USE WHEN: ...' to get_user_summary description."""
        agent = create_agent(base_url="http://fake:8080")

        td = ToolDefinition(
            name="get_user_summary",
            description="Get user activity summaries.",
            parameters_json_schema={"type": "object", "properties": {}},
        )

        ctx = MagicMock()
        updated = await agent._prepare_tools(ctx, [td])

        assert len(updated) == 1
        assert "USE WHEN:" in updated[0].description
        assert updated[0].name == "get_user_summary"

    @pytest.mark.asyncio
    async def test_all_three_tools_get_use_when_suffix(self):
        """inject_signposts() rewrites descriptions for all three registered tools."""
        agent = create_agent(base_url="http://fake:8080")

        tool_defs = [
            ToolDefinition(
                name="web_search",
                description="Search the web.",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            ),
            ToolDefinition(
                name="search_history",
                description="Search channel history.",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            ),
            ToolDefinition(
                name="get_user_summary",
                description="Get user summaries.",
                parameters_json_schema={"type": "object", "properties": {}},
            ),
        ]

        ctx = MagicMock()
        updated = await agent._prepare_tools(ctx, tool_defs)

        assert len(updated) == 3
        for td in updated:
            assert "USE WHEN:" in td.description, (
                f"Tool '{td.name}' description missing 'USE WHEN:': {td.description!r}"
            )

    @pytest.mark.asyncio
    async def test_original_description_is_preserved_before_use_when(self):
        """inject_signposts() keeps the original description before the 'USE WHEN:' suffix."""
        agent = create_agent(base_url="http://fake:8080")
        original_desc = "Search the web for current information."

        td = ToolDefinition(
            name="web_search",
            description=original_desc,
            parameters_json_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        )

        ctx = MagicMock()
        updated = await agent._prepare_tools(ctx, [td])

        assert updated[0].description.startswith(original_desc)

    @pytest.mark.asyncio
    async def test_unknown_tool_name_passthrough_unchanged(self):
        """inject_signposts() passes through ToolDefinitions for unknown tool names unchanged."""
        agent = create_agent(base_url="http://fake:8080")
        original_desc = "Some hypothetical tool."

        td = ToolDefinition(
            name="nonexistent_tool",
            description=original_desc,
            parameters_json_schema={"type": "object", "properties": {}},
        )

        ctx = MagicMock()
        updated = await agent._prepare_tools(ctx, [td])

        assert len(updated) == 1
        assert updated[0].description == original_desc
        assert "USE WHEN:" not in updated[0].description

    @pytest.mark.asyncio
    async def test_empty_tool_list_returns_empty_list(self):
        """inject_signposts() returns an empty list when given no tool definitions."""
        agent = create_agent(base_url="http://fake:8080")
        ctx = MagicMock()
        updated = await agent._prepare_tools(ctx, [])
        assert updated == []
