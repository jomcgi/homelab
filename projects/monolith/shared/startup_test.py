from unittest.mock import MagicMock, patch

import pytest

from shared import service


@pytest.mark.asyncio
async def test_calendar_poll_handler_calls_poll_calendar():
    """calendar_poll_handler delegates to poll_calendar and returns None."""
    with patch.object(service, "poll_calendar") as mock_poll:
        mock_poll.return_value = None
        result = await service.calendar_poll_handler(MagicMock())
        mock_poll.assert_called_once()
        assert result is None


def test_on_startup_registers_job():
    """on_startup registers the shared.calendar_poll job with correct parameters."""
    mock_session = MagicMock()
    with patch("shared.scheduler.register_job") as mock_register:
        service.on_startup(mock_session)
        mock_register.assert_called_once_with(
            mock_session,
            name="shared.calendar_poll",
            interval_secs=900,
            handler=service.calendar_poll_handler,
            ttl_secs=120,
        )
