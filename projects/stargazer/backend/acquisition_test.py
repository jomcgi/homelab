"""Unit tests for the acquisition module."""

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from projects.stargazer.backend.acquisition import (
    download_colorbar,
    download_dem,
    download_file,
    download_lp_atlas,
    download_osm_roads,
)
from projects.stargazer.backend.config import BoundsConfig, EuropeBoundsConfig, Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        bounds=BoundsConfig(),
        europe_bounds=EuropeBoundsConfig(),
        otel_enabled=False,
    )


def make_stream_mock(content: bytes, raise_on_status: Exception | None = None):
    """Build a context-manager mock that behaves like httpx streaming."""
    mock_response = MagicMock()
    if raise_on_status:
        mock_response.raise_for_status.side_effect = raise_on_status
    else:
        mock_response.raise_for_status = MagicMock()

    async def _aiter_bytes():
        yield content

    mock_response.aiter_bytes = _aiter_bytes

    @asynccontextmanager
    async def _stream(*args, **kwargs):
        yield mock_response

    return _stream


# ---------------------------------------------------------------------------
# download_file
# ---------------------------------------------------------------------------


class TestDownloadFile:
    """Tests for download_file."""

    @pytest.mark.asyncio
    async def test_skip_when_dest_exists(self, tmp_path: Path):
        """Existing destination skips the HTTP request entirely."""
        dest = tmp_path / "already_there.dat"
        dest.write_bytes(b"old content")

        client = AsyncMock()
        result = await download_file("https://example.com/f", dest, client)

        assert result == dest
        client.stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_downloads_content(self, tmp_path: Path):
        """Missing destination triggers HTTP download and writes bytes."""
        dest = tmp_path / "new.dat"
        content = b"hello world"

        client = MagicMock()
        client.stream = make_stream_mock(content)

        result = await download_file("https://example.com/f", dest, client)

        assert result == dest
        assert dest.read_bytes() == content

    @pytest.mark.asyncio
    async def test_creates_parent_directories(self, tmp_path: Path):
        """Parent directories are created automatically if missing."""
        dest = tmp_path / "a" / "b" / "c" / "file.dat"
        client = MagicMock()
        client.stream = make_stream_mock(b"data")

        await download_file("https://example.com/f", dest, client)

        assert dest.parent.exists()
        assert dest.exists()

    @pytest.mark.asyncio
    async def test_propagates_http_error(self, tmp_path: Path):
        """HTTPStatusError from raise_for_status should propagate."""
        dest = tmp_path / "file.dat"
        error = httpx.HTTPStatusError(
            "404",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
        client = MagicMock()
        client.stream = make_stream_mock(b"", raise_on_status=error)

        with pytest.raises(httpx.HTTPStatusError):
            await download_file("https://example.com/f", dest, client)

    @pytest.mark.asyncio
    async def test_returns_dest_path(self, tmp_path: Path):
        """Return value should be the dest Path."""
        dest = tmp_path / "out.bin"
        client = MagicMock()
        client.stream = make_stream_mock(b"x")

        result = await download_file("https://example.com/f", dest, client)

        assert result is dest

    @pytest.mark.asyncio
    async def test_handles_empty_response(self, tmp_path: Path):
        """Empty content is written without error."""
        dest = tmp_path / "empty.dat"
        client = MagicMock()
        client.stream = make_stream_mock(b"")

        await download_file("https://example.com/f", dest, client)

        assert dest.exists()
        assert dest.stat().st_size == 0

    @pytest.mark.asyncio
    async def test_logs_warning_on_skip(self, tmp_path: Path):
        """A log message is emitted when an existing file is skipped."""
        dest = tmp_path / "exists.dat"
        dest.write_bytes(b"x")

        with patch("projects.stargazer.backend.acquisition.logger") as mock_log:
            await download_file("https://example.com/f", dest, AsyncMock())

        mock_log.info.assert_called()

    @pytest.mark.asyncio
    async def test_logs_download_start(self, tmp_path: Path):
        """A log message is emitted when download begins."""
        dest = tmp_path / "new.dat"
        with patch("projects.stargazer.backend.acquisition.logger") as mock_log:
            client = MagicMock()
            client.stream = make_stream_mock(b"data")
            await download_file("https://example.com/f", dest, client)

        assert mock_log.info.call_count >= 2  # "Downloading" + "Downloaded"


# ---------------------------------------------------------------------------
# download_lp_atlas
# ---------------------------------------------------------------------------


class TestDownloadLpAtlas:
    """Tests for download_lp_atlas."""

    @pytest.mark.asyncio
    async def test_destination_is_under_raw_dir(self, tmp_path: Path):
        """LP atlas should land in raw_dir/Europe2024.png."""
        settings = make_settings(tmp_path)
        dest = settings.raw_dir / "Europe2024.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.touch()  # pre-create to avoid network call

        result = await download_lp_atlas(settings, AsyncMock())

        assert result == dest
        assert result.parent == settings.raw_dir

    @pytest.mark.asyncio
    async def test_uses_djlorenz_url(self, tmp_path: Path):
        """The configured URL should point to djlorenz source."""
        settings = make_settings(tmp_path)
        assert "djlorenz" in settings.lp_source_url
        assert "Europe2024.png" in settings.lp_source_url


# ---------------------------------------------------------------------------
# download_colorbar
# ---------------------------------------------------------------------------


class TestDownloadColorbar:
    """Tests for download_colorbar."""

    @pytest.mark.asyncio
    async def test_destination_is_colorbar_png(self, tmp_path: Path):
        """Colorbar should land in raw_dir/colorbar.png."""
        settings = make_settings(tmp_path)
        dest = settings.raw_dir / "colorbar.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.touch()

        result = await download_colorbar(settings, AsyncMock())

        assert result == dest

    @pytest.mark.asyncio
    async def test_url_contains_colorbar(self, tmp_path: Path):
        """The configured URL should reference 'colorbar.png'."""
        settings = make_settings(tmp_path)
        assert "colorbar.png" in settings.colorbar_url


# ---------------------------------------------------------------------------
# download_osm_roads
# ---------------------------------------------------------------------------


class TestDownloadOsmRoads:
    """Tests for download_osm_roads."""

    @pytest.mark.asyncio
    async def test_destination_is_pbf_file(self, tmp_path: Path):
        """OSM roads should land in raw_dir/scotland-latest.osm.pbf."""
        settings = make_settings(tmp_path)
        dest = settings.raw_dir / "scotland-latest.osm.pbf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.touch()

        result = await download_osm_roads(settings, AsyncMock())

        assert result == dest

    @pytest.mark.asyncio
    async def test_url_is_geofabrik_scotland(self, tmp_path: Path):
        """The configured URL should use geofabrik and reference scotland."""
        settings = make_settings(tmp_path)
        assert "geofabrik" in settings.osm_source_url
        assert "scotland" in settings.osm_source_url


# ---------------------------------------------------------------------------
# download_dem
# ---------------------------------------------------------------------------


class TestDownloadDem:
    """Tests for download_dem (placeholder implementation)."""

    @pytest.mark.asyncio
    async def test_creates_srtm_tiles_directory(self, tmp_path: Path):
        """Should create and return raw_dir/srtm_tiles directory."""
        settings = make_settings(tmp_path)

        result = await download_dem(settings)

        assert result == settings.raw_dir / "srtm_tiles"
        assert result.is_dir()

    @pytest.mark.asyncio
    async def test_result_is_under_raw_dir(self, tmp_path: Path):
        """Result path parent should be raw_dir."""
        settings = make_settings(tmp_path)
        result = await download_dem(settings)
        assert result.parent == settings.raw_dir

    @pytest.mark.asyncio
    async def test_logs_not_implemented_warning(self, tmp_path: Path):
        """Should log a warning about unimplemented DEM download."""
        settings = make_settings(tmp_path)
        with patch("projects.stargazer.backend.acquisition.logger") as mock_log:
            await download_dem(settings)

        mock_log.warning.assert_called_once()
        warning_text = mock_log.warning.call_args[0][0].lower()
        assert "not yet implemented" in warning_text or "placeholder" in warning_text

    @pytest.mark.asyncio
    async def test_idempotent_on_repeated_calls(self, tmp_path: Path):
        """Calling download_dem twice should not raise (directory already exists)."""
        settings = make_settings(tmp_path)

        first = await download_dem(settings)
        second = await download_dem(settings)

        assert first == second
        assert second.is_dir()


# ---------------------------------------------------------------------------
# Integration: all downloads share the raw_dir parent
# ---------------------------------------------------------------------------


class TestDownloadIntegration:
    """Integration-level checks that all downloads land in raw_dir."""

    @pytest.mark.asyncio
    async def test_all_outputs_under_raw_dir(self, tmp_path: Path):
        """All download helpers should place files under settings.raw_dir."""
        settings = make_settings(tmp_path)
        settings.raw_dir.mkdir(parents=True, exist_ok=True)

        # Pre-create files to skip actual network calls
        (settings.raw_dir / "Europe2024.png").touch()
        (settings.raw_dir / "colorbar.png").touch()
        (settings.raw_dir / "scotland-latest.osm.pbf").touch()

        client = AsyncMock()

        lp = await download_lp_atlas(settings, client)
        cb = await download_colorbar(settings, client)
        osm = await download_osm_roads(settings, client)
        dem = await download_dem(settings)

        for result in (lp, cb, osm, dem):
            assert result.parent == settings.raw_dir or result == settings.raw_dir / "srtm_tiles"
