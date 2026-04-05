"""Behavioral tests for inject_signposts() and tool_guidance() in agent.py.

inject_signposts() is the prepare_tools callback that rewrites each tool's
ToolDefinition description to append 'USE WHEN: <signpost>' at runtime.

tool_guidance() is a system_prompt function registered on the agent that
dynamically builds a per-tool usage guide from the signpost attributes.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import ToolDefinition
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, TextPart

from chat.agent import ChatDeps, create_agent


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


# ---------------------------------------------------------------------------
# tool_guidance() dynamic system prompt tests
# ---------------------------------------------------------------------------


class TestToolGuidanceSystemPrompt:
    @pytest.mark.asyncio
    async def test_system_prompt_contains_your_tools_header(self):
        """tool_guidance() generates a system prompt containing the tools header."""
        agent = create_agent(base_url="http://fake:8080")
        system_parts: list[str] = []

        def capture_model(messages, info):
            for msg in messages:
                if hasattr(msg, "parts"):
                    for part in msg.parts:
                        if hasattr(part, "content") and hasattr(part, "part_kind"):
                            if part.part_kind == "system-prompt":
                                system_parts.append(part.content)
            return ModelResponse(parts=[TextPart("done")])

        deps = ChatDeps(
            channel_id="ch1",
            store=MagicMock(),
            embed_client=AsyncMock(),
        )
        await agent.run("hi", model=FunctionModel(capture_model), deps=deps)

        combined = "\n".join(system_parts)
        assert "Your tools and WHEN to use them:" in combined

    @pytest.mark.asyncio
    async def test_system_prompt_lists_web_search_with_use_when(self):
        """tool_guidance() includes 'web_search' and its signpost in the system prompt."""
        agent = create_agent(base_url="http://fake:8080")
        system_parts: list[str] = []

        def capture_model(messages, info):
            for msg in messages:
                if hasattr(msg, "parts"):
                    for part in msg.parts:
                        if hasattr(part, "content") and hasattr(part, "part_kind"):
                            if part.part_kind == "system-prompt":
                                system_parts.append(part.content)
            return ModelResponse(parts=[TextPart("done")])

        deps = ChatDeps(
            channel_id="ch1",
            store=MagicMock(),
            embed_client=AsyncMock(),
        )
        await agent.run("hi", model=FunctionModel(capture_model), deps=deps)

        combined = "\n".join(system_parts)
        assert "web_search" in combined
        assert "USE WHEN:" in combined

    @pytest.mark.asyncio
    async def test_system_prompt_lists_all_three_tool_names(self):
        """tool_guidance() includes all three tool names in the system prompt."""
        agent = create_agent(base_url="http://fake:8080")
        system_parts: list[str] = []

        def capture_model(messages, info):
            for msg in messages:
                if hasattr(msg, "parts"):
                    for part in msg.parts:
                        if hasattr(part, "content") and hasattr(part, "part_kind"):
                            if part.part_kind == "system-prompt":
                                system_parts.append(part.content)
            return ModelResponse(parts=[TextPart("done")])

        deps = ChatDeps(
            channel_id="ch1",
            store=MagicMock(),
            embed_client=AsyncMock(),
        )
        await agent.run("hi", model=FunctionModel(capture_model), deps=deps)

        combined = "\n".join(system_parts)
        assert "web_search" in combined
        assert "search_history" in combined
        assert "get_user_summary" in combined

    @pytest.mark.asyncio
    async def test_system_prompt_includes_signpost_text_for_web_search(self):
        """tool_guidance() includes part of the web_search signpost text."""
        agent = create_agent(base_url="http://fake:8080")
        system_parts: list[str] = []

        def capture_model(messages, info):
            for msg in messages:
                if hasattr(msg, "parts"):
                    for part in msg.parts:
                        if hasattr(part, "content") and hasattr(part, "part_kind"):
                            if part.part_kind == "system-prompt":
                                system_parts.append(part.content)
            return ModelResponse(parts=[TextPart("done")])

        deps = ChatDeps(
            channel_id="ch1",
            store=MagicMock(),
            embed_client=AsyncMock(),
        )
        await agent.run("hi", model=FunctionModel(capture_model), deps=deps)

        # web_search signpost says "Default to searching"
        combined = "\n".join(system_parts)
        assert "Default to searching" in combined
