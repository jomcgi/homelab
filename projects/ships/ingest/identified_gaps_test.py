"""
Tests for identified coverage gaps in AIS ingest service.

Covers:
5. connect_nats() update_stream failure propagation — if the "already in use"
   recovery path itself raises, the exception propagates uncaught (no test existed)
6. publish_static() counter asymmetry — unlike publish_position(), publish_static()
   does NOT increment messages_published or update last_message_time
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# 5. connect_nats() update_stream failure propagation
# ---------------------------------------------------------------------------


class TestConnectNatsUpdateStreamFailure:
    """When connect_nats() enters the 'already in use' recovery path but
    update_stream() itself raises, the exception propagates uncaught."""

    @pytest.mark.asyncio
    async def test_update_stream_error_propagates(self):
        """If update_stream raises after the 'already in use' add_stream error,
        the exception bubbles out of connect_nats() uncaught."""
        import nats as nats_module
        import nats.js.errors

        from projects.ships.ingest.main import AISIngestService

        class _AlreadyInUse(nats.js.errors.BadRequestError):
            def __str__(self):
                return "stream name already in use"

        service = AISIngestService()
        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js
        mock_js.add_stream.side_effect = _AlreadyInUse()
        mock_js.update_stream.side_effect = RuntimeError(
            "NATS update rejected: quota exceeded"
        )

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            with pytest.raises(RuntimeError, match="quota exceeded"):
                await service.connect_nats()

    @pytest.mark.asyncio
    async def test_update_stream_os_error_propagates(self):
        """OSError from update_stream is not caught — propagates to caller."""
        import nats as nats_module
        import nats.js.errors

        from projects.ships.ingest.main import AISIngestService

        class _AlreadyInUse(nats.js.errors.BadRequestError):
            def __str__(self):
                return "already in use"

        service = AISIngestService()
        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js
        mock_js.add_stream.side_effect = _AlreadyInUse()
        mock_js.update_stream.side_effect = OSError("connection reset")

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            with pytest.raises(OSError, match="connection reset"):
                await service.connect_nats()

    @pytest.mark.asyncio
    async def test_update_stream_value_error_propagates(self):
        """ValueError from update_stream is not swallowed — propagates."""
        import nats as nats_module
        import nats.js.errors

        from projects.ships.ingest.main import AISIngestService

        class _AlreadyInUse(nats.js.errors.BadRequestError):
            def __str__(self):
                return "stream name already in use"

        service = AISIngestService()
        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js
        mock_js.add_stream.side_effect = _AlreadyInUse()
        mock_js.update_stream.side_effect = ValueError("bad stream config")

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            with pytest.raises(ValueError, match="bad stream config"):
                await service.connect_nats()

    @pytest.mark.asyncio
    async def test_update_stream_success_does_not_raise(self):
        """When update_stream succeeds after 'already in use', connect_nats() completes
        without error — baseline sanity check."""
        import nats as nats_module
        import nats.js.errors

        from projects.ships.ingest.main import AISIngestService

        class _AlreadyInUse(nats.js.errors.BadRequestError):
            def __str__(self):
                return "stream name already in use"

        service = AISIngestService()
        mock_nc = MagicMock()
        mock_js = AsyncMock()
        mock_nc.jetstream.return_value = mock_js
        mock_js.add_stream.side_effect = _AlreadyInUse()
        # update_stream returns normally (no side_effect = returns AsyncMock default)

        with patch.object(nats_module, "connect", AsyncMock(return_value=mock_nc)):
            await service.connect_nats()  # Must not raise

        mock_js.update_stream.assert_called_once()


# ---------------------------------------------------------------------------
# 6. publish_static() counter asymmetry vs publish_position()
# ---------------------------------------------------------------------------


class TestPublishStaticCounterAsymmetry:
    """publish_static() does NOT increment messages_published and does NOT
    update last_message_time — unlike publish_position() which does both."""

    @pytest.mark.asyncio
    async def test_publish_static_does_not_increment_messages_published(self):
        """After calling publish_static(), messages_published remains 0."""
        from projects.ships.ingest.main import AISIngestService

        service = AISIngestService()
        service.js = AsyncMock()

        data = {
            "mmsi": "123456789",
            "name": "TEST VESSEL",
            "timestamp": "2027-01-01T00:00:00Z",
        }
        await service.publish_static("123456789", data)

        assert service.messages_published == 0

    @pytest.mark.asyncio
    async def test_publish_static_does_not_update_last_message_time(self):
        """After calling publish_static(), last_message_time remains None."""
        from projects.ships.ingest.main import AISIngestService

        service = AISIngestService()
        service.js = AsyncMock()

        data = {
            "mmsi": "123456789",
            "name": "TEST",
            "timestamp": "2027-01-01T00:00:00Z",
        }
        await service.publish_static("123456789", data)

        assert service.last_message_time is None

    @pytest.mark.asyncio
    async def test_publish_position_increments_messages_published(self):
        """Contrast: publish_position() DOES increment messages_published."""
        from projects.ships.ingest.main import AISIngestService

        service = AISIngestService()
        service.js = AsyncMock()

        data = {
            "mmsi": "123456789",
            "lat": 48.5,
            "lon": -123.4,
            "timestamp": "2027-01-01T00:00:00Z",
        }
        await service.publish_position("123456789", data)

        assert service.messages_published == 1

    @pytest.mark.asyncio
    async def test_publish_position_updates_last_message_time(self):
        """Contrast: publish_position() DOES update last_message_time."""
        from projects.ships.ingest.main import AISIngestService

        service = AISIngestService()
        service.js = AsyncMock()

        ts = "2027-01-01T00:00:00Z"
        data = {"mmsi": "123456789", "lat": 48.5, "lon": -123.4, "timestamp": ts}
        await service.publish_position("123456789", data)

        assert service.last_message_time == ts

    @pytest.mark.asyncio
    async def test_counter_asymmetry_multiple_calls(self):
        """After N publish_static() + M publish_position() calls, only the M
        position calls are counted in messages_published."""
        from projects.ships.ingest.main import AISIngestService

        service = AISIngestService()
        service.js = AsyncMock()

        static_data = {
            "mmsi": "111",
            "name": "VESSEL",
            "timestamp": "2027-01-01T00:00:00Z",
        }
        pos_data = {
            "mmsi": "111",
            "lat": 48.5,
            "lon": -123.4,
            "timestamp": "2027-01-01T00:01:00Z",
        }

        # 3 static publishes (should NOT count)
        await service.publish_static("111", static_data)
        await service.publish_static("111", static_data)
        await service.publish_static("111", static_data)

        # 2 position publishes (SHOULD count)
        await service.publish_position("111", pos_data)
        await service.publish_position(
            "111", {**pos_data, "timestamp": "2027-01-01T00:02:00Z"}
        )

        # Only the 2 position publishes should be counted
        assert service.messages_published == 2
        # last_message_time reflects only position publishes
        assert service.last_message_time == "2027-01-01T00:02:00Z"
