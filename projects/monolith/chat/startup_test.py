from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat import summarizer
from shared.scheduler import _registry


@pytest.fixture(autouse=True)
def _clear_registry():
    """Clear the scheduler registry before and after each test."""
    _registry.clear()
    yield
    _registry.clear()


def test_on_startup_without_bot_skips_changelog():
    """Calling on_startup without bot registers only summary_generation."""
    session = MagicMock()
    llm_call = AsyncMock()

    with patch("shared.scheduler.register_job") as mock_register:
        summarizer.on_startup(session, llm_call=llm_call)

    assert mock_register.call_count == 1
    call_kwargs = mock_register.call_args_list[0]
    assert call_kwargs[1]["name"] == "chat.summary_generation"


def test_on_startup_with_bot_registers_both():
    """Calling on_startup with bot registers both summary_generation and changelog."""
    session = MagicMock()
    bot = MagicMock()
    llm_call = AsyncMock()

    with patch("shared.scheduler.register_job") as mock_register:
        summarizer.on_startup(session, bot=bot, llm_call=llm_call)

    assert mock_register.call_count == 2
    names = {call[1]["name"] for call in mock_register.call_args_list}
    assert names == {"chat.summary_generation", "chat.changelog"}


@pytest.mark.asyncio
async def test_summary_handler_calls_generate_functions():
    """The summary handler calls generate_summaries and generate_channel_summaries."""
    session = MagicMock()
    llm_call = AsyncMock()

    with patch("shared.scheduler.register_job", side_effect=lambda _s, **kw: _registry.__setitem__(kw["name"], kw["handler"])):
        summarizer.on_startup(session, llm_call=llm_call)

    handler = _registry["chat.summary_generation"]

    with (
        patch.object(summarizer, "generate_summaries", new_callable=AsyncMock) as mock_gen,
        patch.object(summarizer, "generate_channel_summaries", new_callable=AsyncMock) as mock_chan,
    ):
        await handler(session)

    mock_gen.assert_called_once_with(session, llm_call)
    mock_chan.assert_called_once_with(session, llm_call)


@pytest.mark.asyncio
async def test_changelog_handler_calls_run_changelog_iteration():
    """The changelog handler calls run_changelog_iteration with bot and llm_call."""
    session = MagicMock()
    bot = MagicMock()
    llm_call = AsyncMock()

    with patch("shared.scheduler.register_job", side_effect=lambda _s, **kw: _registry.__setitem__(kw["name"], kw["handler"])):
        summarizer.on_startup(session, bot=bot, llm_call=llm_call)

    handler = _registry["chat.changelog"]

    with patch("chat.changelog.run_changelog_iteration", new_callable=AsyncMock) as mock_iter:
        await handler(session)

    mock_iter.assert_called_once_with(bot, llm_call)
