"""Tests for detect-wildlife/main.py — GoPro I/O functions.

Covers:
- configure_gopro: camera settings (PRO mode, photo preset, lens, RAW, GPS)
- capture_photo: shutter trigger, new media detection, queue insertion
- connect_gopro: connection retry logic, context manager lifecycle
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401 — registers plugin

from main import (
    CaptureQueue,
    PerfStats,
    GracefulShutdown,
    capture_photo,
    configure_gopro,
    connect_gopro,
)


# ---------------------------------------------------------------------------
# configure_gopro
# ---------------------------------------------------------------------------


def _make_gopro():
    """Build a minimal WiredGoPro mock with async settings."""
    gopro = MagicMock()

    # http_setting attributes used by configure_gopro
    for attr in [
        "control_mode",
        "photo_lens",
        "photo_output",
        "photo_single_interval",
        "gps",
    ]:
        setting = MagicMock()
        result = MagicMock()
        result.ok = True
        setting.set = AsyncMock(return_value=result)
        setattr(gopro.http_setting, attr, setting)

    # http_command.load_preset_group
    gopro.http_command.load_preset_group = AsyncMock()

    return gopro


class TestConfigureGopro:
    """Camera configuration sequence."""

    @pytest.mark.asyncio
    async def test_sets_control_mode_pro(self):
        gopro = _make_gopro()
        await configure_gopro(gopro)
        gopro.http_setting.control_mode.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_loads_photo_preset_group(self):
        gopro = _make_gopro()
        await configure_gopro(gopro)
        gopro.http_command.load_preset_group.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sets_photo_lens(self):
        gopro = _make_gopro()
        await configure_gopro(gopro)
        gopro.http_setting.photo_lens.set.assert_awaited()

    @pytest.mark.asyncio
    async def test_sets_photo_output_raw(self):
        gopro = _make_gopro()
        await configure_gopro(gopro)
        gopro.http_setting.photo_output.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sets_photo_single_interval_off(self):
        gopro = _make_gopro()
        await configure_gopro(gopro)
        gopro.http_setting.photo_single_interval.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enables_gps(self):
        gopro = _make_gopro()
        await configure_gopro(gopro)
        gopro.http_setting.gps.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_test_mode_does_not_raise(self):
        """test_mode=True adds debug prints but must not crash."""
        gopro = _make_gopro()
        await configure_gopro(gopro, test_mode=True)

    @pytest.mark.asyncio
    async def test_stops_trying_lens_options_after_first_success(self):
        """Only tries further lens options if the first one fails."""
        gopro = _make_gopro()

        # First lens attempt succeeds
        first_result = MagicMock()
        first_result.ok = True
        gopro.http_setting.photo_lens.set = AsyncMock(return_value=first_result)

        await configure_gopro(gopro)

        # Should have been called exactly once (stopped after success)
        gopro.http_setting.photo_lens.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tries_next_lens_when_first_fails(self):
        """Falls through to next lens option when first fails."""
        gopro = _make_gopro()

        fail_result = MagicMock()
        fail_result.ok = False
        success_result = MagicMock()
        success_result.ok = True

        gopro.http_setting.photo_lens.set = AsyncMock(
            side_effect=[fail_result, success_result]
        )

        await configure_gopro(gopro)
        assert gopro.http_setting.photo_lens.set.await_count == 2


# ---------------------------------------------------------------------------
# capture_photo
# ---------------------------------------------------------------------------


def _media_entry(name: str):
    """Create a fake media list entry with a .filename attribute."""
    entry = MagicMock()
    entry.filename = name
    return entry


class TestCapturePhoto:
    """Shutter trigger, new media detection, and queue recording."""

    def _make_gopro_for_capture(self, media_after: set):
        gopro = MagicMock()

        # Shutter trigger
        shutter_result = MagicMock()
        shutter_result.ok = True
        gopro.http_command.set_shutter = AsyncMock(return_value=shutter_result)

        # Media list returns media_after
        media_list_response = MagicMock()
        media_list_response.data.files = media_after
        gopro.http_command.get_media_list = AsyncMock(return_value=media_list_response)

        return gopro

    @pytest.mark.asyncio
    async def test_triggers_shutter(self, tmp_path):
        media_before = set()
        new_entry = _media_entry("GOPR0001.JPG")
        gopro = self._make_gopro_for_capture({new_entry})

        queue = CaptureQueue(tmp_path / "q.db")
        event = asyncio.Event()

        await capture_photo(gopro, queue, tmp_path, media_before, event)
        gopro.http_command.set_shutter.assert_awaited()

    @pytest.mark.asyncio
    async def test_adds_new_photo_to_queue(self, tmp_path):
        media_before = set()
        new_entry = _media_entry("GOPR0001.JPG")
        gopro = self._make_gopro_for_capture({new_entry})

        queue = CaptureQueue(tmp_path / "q.db")
        event = asyncio.Event()

        await capture_photo(gopro, queue, tmp_path, media_before, event)
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0].camera_filename == "GOPR0001.JPG"

    @pytest.mark.asyncio
    async def test_raises_when_no_new_photo(self, tmp_path):
        """Raises RuntimeError if the media list doesn't change."""
        existing = _media_entry("GOPR0001.JPG")
        media_before = {existing}
        # media_after is the same — no new photo
        gopro = self._make_gopro_for_capture(media_before.copy())

        queue = CaptureQueue(tmp_path / "q.db")
        event = asyncio.Event()

        with pytest.raises(RuntimeError, match="No new photo"):
            await capture_photo(gopro, queue, tmp_path, media_before, event)

    @pytest.mark.asyncio
    async def test_sets_download_event(self, tmp_path):
        media_before = set()
        new_entry = _media_entry("GOPR0001.JPG")
        gopro = self._make_gopro_for_capture({new_entry})

        queue = CaptureQueue(tmp_path / "q.db")
        event = asyncio.Event()
        assert not event.is_set()

        await capture_photo(gopro, queue, tmp_path, media_before, event)
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_returns_updated_media_set(self, tmp_path):
        media_before = set()
        new_entry = _media_entry("GOPR0002.JPG")
        media_after = {new_entry}
        gopro = self._make_gopro_for_capture(media_after)

        queue = CaptureQueue(tmp_path / "q.db")
        event = asyncio.Event()

        returned_media, _capture_time = await capture_photo(
            gopro, queue, tmp_path, media_before, event
        )
        assert new_entry in returned_media

    @pytest.mark.asyncio
    async def test_returns_capture_time_float(self, tmp_path):
        media_before = set()
        new_entry = _media_entry("GOPR0001.JPG")
        gopro = self._make_gopro_for_capture({new_entry})

        queue = CaptureQueue(tmp_path / "q.db")
        event = asyncio.Event()

        _, capture_time = await capture_photo(gopro, queue, tmp_path, media_before, event)
        assert isinstance(capture_time, float)
        assert capture_time >= 0

    @pytest.mark.asyncio
    async def test_records_capture_in_stats(self, tmp_path):
        media_before = set()
        new_entry = _media_entry("GOPR0001.JPG")
        gopro = self._make_gopro_for_capture({new_entry})

        queue = CaptureQueue(tmp_path / "q.db")
        event = asyncio.Event()
        stats = PerfStats()

        await capture_photo(gopro, queue, tmp_path, media_before, event, stats)
        assert len(stats.capture_times) == 1

    @pytest.mark.asyncio
    async def test_retries_shutter_on_failure_then_succeeds(self, tmp_path):
        """Shutter is retried up to 3 times before raising."""
        media_before = set()
        new_entry = _media_entry("GOPR0001.JPG")
        gopro = self._make_gopro_for_capture({new_entry})

        # Fail first attempt, succeed on second
        success = MagicMock()
        success.ok = True
        gopro.http_command.set_shutter = AsyncMock(
            side_effect=[Exception("busy"), success]
        )

        queue = CaptureQueue(tmp_path / "q.db")
        event = asyncio.Event()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await capture_photo(gopro, queue, tmp_path, media_before, event)

        assert gopro.http_command.set_shutter.await_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_all_shutter_retries_exhausted(self, tmp_path):
        """After 3 failed shutter attempts, the exception propagates."""
        gopro = MagicMock()
        gopro.http_command.set_shutter = AsyncMock(side_effect=Exception("always busy"))

        # get_media_list won't be reached, but must be callable
        gopro.http_command.get_media_list = AsyncMock()

        queue = CaptureQueue(tmp_path / "q.db")
        event = asyncio.Event()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception, match="always busy"):
                await capture_photo(gopro, queue, tmp_path, set(), event)


# ---------------------------------------------------------------------------
# connect_gopro
# ---------------------------------------------------------------------------


class TestConnectGopro:
    """Context manager that connects to GoPro with retry."""

    @pytest.mark.asyncio
    async def test_yields_gopro_instance_on_success(self):
        mock_gopro = MagicMock()
        mock_gopro.open = AsyncMock()
        mock_gopro.close = AsyncMock()

        with patch("main.WiredGoPro", return_value=mock_gopro):
            async with connect_gopro() as gopro:
                assert gopro is mock_gopro

    @pytest.mark.asyncio
    async def test_closes_gopro_on_exit(self):
        mock_gopro = MagicMock()
        mock_gopro.open = AsyncMock()
        mock_gopro.close = AsyncMock()

        with patch("main.WiredGoPro", return_value=mock_gopro):
            async with connect_gopro():
                pass

        mock_gopro.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_closes_gopro_even_if_body_raises(self):
        mock_gopro = MagicMock()
        mock_gopro.open = AsyncMock()
        mock_gopro.close = AsyncMock()

        with patch("main.WiredGoPro", return_value=mock_gopro):
            with pytest.raises(ValueError):
                async with connect_gopro():
                    raise ValueError("body error")

        mock_gopro.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retries_on_connection_failure(self):
        """Retries up to 5 times before giving up."""
        mock_gopro = MagicMock()
        # Fail twice, succeed on third attempt
        mock_gopro.open = AsyncMock(
            side_effect=[Exception("refused"), Exception("refused"), None]
        )
        mock_gopro.close = AsyncMock()

        with patch("main.WiredGoPro", return_value=mock_gopro), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            async with connect_gopro():
                pass

        assert mock_gopro.open.await_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_five_failures(self):
        """Raises after exhausting all 5 retries."""
        mock_gopro = MagicMock()
        mock_gopro.open = AsyncMock(side_effect=Exception("unreachable"))
        mock_gopro.close = AsyncMock()

        with patch("main.WiredGoPro", return_value=mock_gopro), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception, match="unreachable"):
                async with connect_gopro():
                    pass

        assert mock_gopro.open.await_count == 5

    @pytest.mark.asyncio
    async def test_test_mode_does_not_raise(self):
        mock_gopro = MagicMock()
        mock_gopro.open = AsyncMock()
        mock_gopro.close = AsyncMock()

        with patch("main.WiredGoPro", return_value=mock_gopro):
            async with connect_gopro(test_mode=True) as gopro:
                assert gopro is mock_gopro
