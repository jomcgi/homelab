"""Tests for the web_search tool body in the PydanticAI chat agent.

The existing agent_tool_execution_test.py covers search_history and
get_user_summary via FunctionModel, but the web_search tool body
(which delegates to search_web()) was untested. These tests drive the
actual tool execution path using pydantic_ai's FunctionModel.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from chat.agent import ChatDeps, create_agent


def _make_deps(
    store: MagicMock | None = None,
    embed_client: AsyncMock | None = None,
    channel_id: str = "ch1",
) -> ChatDeps:
    return ChatDeps(
        channel_id=channel_id,
        store=store or MagicMock(),
        embed_client=embed_client or AsyncMock(),
    )


def _tool_once_then_done(tool_name: str, args: dict) -> object:
    """Return a FunctionModel that calls one tool then returns 'done'."""

    def model_func(messages, info):  # type: ignore[type-arg]
        for msg in messages:
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if isinstance(part, ToolReturnPart):
                        return ModelResponse(parts=[TextPart("done")])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=tool_name,
                    args=args,
                    tool_call_id="call-1",
                )
            ]
        )

    return FunctionModel(model_func)


# ---------------------------------------------------------------------------
# web_search tool body — happy path
# ---------------------------------------------------------------------------


class TestWebSearchToolExecution:
    @pytest.mark.asyncio
    async def test_web_search_calls_search_web_with_query(self):
        """web_search tool calls search_web() with the query provided by the model."""
        deps = _make_deps()
        agent = create_agent(base_url="http://fake:8080")

        with patch("chat.agent.search_web", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = "Some search results about cats"

            await agent.run(
                "What are the latest cat memes?",
                model=_tool_once_then_done("web_search", {"query": "latest cat memes"}),
                deps=deps,
            )

        mock_search.assert_called_once_with("latest cat memes")

    @pytest.mark.asyncio
    async def test_web_search_returns_search_web_result(self):
        """web_search tool returns the string produced by search_web()."""
        deps = _make_deps()
        agent = create_agent(base_url="http://fake:8080")

        tool_returns_captured = []

        def capture_model_func(messages, info):  # type: ignore[type-arg]
            for msg in messages:
                if hasattr(msg, "parts"):
                    for part in msg.parts:
                        if isinstance(part, ToolReturnPart):
                            tool_returns_captured.append(part.content)
                            return ModelResponse(parts=[TextPart("done")])
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="web_search",
                        args={"query": "Mars mission 2026"},
                        tool_call_id="call-1",
                    )
                ]
            )

        with patch("chat.agent.search_web", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = "NASA announces Mars mission for 2026"

            await agent.run(
                "Tell me about Mars missions",
                model=FunctionModel(capture_model_func),
                deps=deps,
            )

        assert len(tool_returns_captured) == 1
        assert tool_returns_captured[0] == "NASA announces Mars mission for 2026"

    @pytest.mark.asyncio
    async def test_web_search_passes_query_string_directly(self):
        """web_search tool passes the query as a plain string to search_web(), not a list."""
        deps = _make_deps()
        agent = create_agent(base_url="http://fake:8080")

        received_queries = []

        async def capture_search(query):
            received_queries.append(query)
            return "results"

        with patch("chat.agent.search_web", side_effect=capture_search):
            await agent.run(
                "Who won the championship?",
                model=_tool_once_then_done(
                    "web_search", {"query": "championship 2026 winner"}
                ),
                deps=deps,
            )

        assert len(received_queries) == 1
        assert received_queries[0] == "championship 2026 winner"
        assert isinstance(received_queries[0], str)


# ---------------------------------------------------------------------------
# web_search tool — propagates search_web() exceptions
# ---------------------------------------------------------------------------


class TestWebSearchToolErrorPropagation:
    @pytest.mark.asyncio
    async def test_web_search_exception_propagates_to_caller(self):
        """web_search tool propagates exceptions from search_web() back through the agent."""
        deps = _make_deps()
        agent = create_agent(base_url="http://fake:8080")

        with patch(
            "chat.agent.search_web",
            new_callable=AsyncMock,
            side_effect=RuntimeError("search service down"),
        ):
            with pytest.raises(RuntimeError, match="search service down"):
                await agent.run(
                    "Search for something",
                    model=_tool_once_then_done("web_search", {"query": "test"}),
                    deps=deps,
                )
