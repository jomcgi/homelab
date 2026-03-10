"""Tests for the acquisition module."""

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
from projects.stargazer.backend.config import Settings


def create_mock_stream_response(
    content: bytes, raise_on_status: Exception | None = None
):
    """Create a properly mocked async stream response."""
    mock_response = MagicMock()
    if raise_on_status:
        mock_response.raise_for_status.side_effect = raise_on_status
    else:
        mock_response.raise_for_status = MagicMock()

    async def aiter_bytes_gen():
        yield content

    mock_response.aiter_bytes = aiter_bytes_gen

    @asynccontextmanager
    async def stream_context(*args, **kwargs):
        yield mock_response

    return stream_context


class TestDownloadFile:
    """Tests for download_file function."""

    @pytest.mark.asyncio
    async def test_skips_if_file_exists(self, tmp_path: Path):
        """Test that download is skipped if file already exists."""
        dest = tmp_path / "existing_file.txt"
        dest.write_text("existing content")

        mock_client = AsyncMock()

        result = await download_file(
            url="https://example.com/file.txt",
            dest=dest,
            client=mock_client,
        )

        assert result == dest
        mock_client.stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_downloads_file(self, tmp_path: Path):
        """Test successful file download."""
        dest = tmp_path / "new_file.txt"
        test_content = b"downloaded content"

        mock_client = MagicMock()
        mock_client.stream = create_mock_stream_response(test_content)

        result = await download_file(
            url="https://example.com/file.txt",
            dest=dest,
            client=mock_client,
        )

        assert result == dest
        assert dest.exists()
        assert dest.read_bytes() == test_content

    @pytest.mark.asyncio
    async def test_creates_parent_directory(self, tmp_path: Path):
        """Test that parent directories are created if needed."""
        dest = tmp_path / "subdir" / "another" / "file.txt"
        test_content = b"content"

        mock_client = MagicMock()
        mock_client.stream = create_mock_stream_response(test_content)

        result = await download_file(
            url="https://example.com/file.txt",
            dest=dest,
            client=mock_client,
        )

        assert dest.parent.exists()
        assert dest.exists()

    @pytest.mark.asyncio
    async def test_handles_http_error(self, tmp_path: Path):
        """Test handling of HTTP errors during download."""
        dest = tmp_path / "file.txt"

        error = httpx.HTTPStatusError(
            "Not found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
        mock_client = MagicMock()
        mock_client.stream = create_mock_stream_response(b"", raise_on_status=error)

        with pytest.raises(httpx.HTTPStatusError):
            await download_file(
                url="https://example.com/file.txt",
                dest=dest,
                client=mock_client,
            )


class TestDownloadLpAtlas:
    """Tests for download_lp_atlas function."""

    @pytest.mark.asyncio
    async def test_downloads_to_correct_path(self, settings: Settings):
        """Test LP atlas is downloaded to correct location."""
        expected_dest = settings.raw_dir / "Europe2024.png"
        expected_dest.parent.mkdir(parents=True, exist_ok=True)
        expected_dest.touch()  # Pre-create to skip download

        mock_client = AsyncMock()

        result = await download_lp_atlas(settings, mock_client)

        assert result == expected_dest

    @pytest.mark.asyncio
    async def test_uses_correct_url(self, settings: Settings):
        """Test that correct URL is used for download."""
        # Verify the URL in settings contains expected source
        assert "djlorenz" in settings.lp_source_url
        assert "Europe2024.png" in settings.lp_source_url


class TestDownloadColorbar:
    """Tests for download_colorbar function."""

    @pytest.mark.asyncio
    async def test_downloads_to_correct_path(self, settings: Settings):
        """Test colorbar is downloaded to correct location."""
        expected_dest = settings.raw_dir / "colorbar.png"
        expected_dest.parent.mkdir(parents=True, exist_ok=True)
        expected_dest.touch()

        mock_client = AsyncMock()

        result = await download_colorbar(settings, mock_client)

        assert result == expected_dest

    @pytest.mark.asyncio
    async def test_uses_correct_url(self, settings: Settings):
        """Test that correct URL is used for colorbar."""
        # Verify the URL in settings contains expected source
        assert "colorbar.png" in settings.colorbar_url


class TestDownloadOsmRoads:
    """Tests for download_osm_roads function."""

    @pytest.mark.asyncio
    async def test_downloads_to_correct_path(self, settings: Settings):
        """Test OSM roads are downloaded to correct location."""
        expected_dest = settings.raw_dir / "scotland-latest.osm.pbf"
        expected_dest.parent.mkdir(parents=True, exist_ok=True)
        expected_dest.touch()

        mock_client = AsyncMock()

        result = await download_osm_roads(settings, mock_client)

        assert result == expected_dest

    @pytest.mark.asyncio
    async def test_uses_geofabrik_url(self, settings: Settings):
        """Test that Geofabrik URL is used for OSM data."""
        # Verify the URL in settings contains expected source
        assert "geofabrik" in settings.osm_source_url
        assert "scotland" in settings.osm_source_url


class TestDownloadDem:
    """Tests for download_dem function."""

    @pytest.mark.asyncio
    async def test_creates_placeholder_directory(self, settings: Settings):
        """Test that placeholder directory is created."""
        result = await download_dem(settings)

        assert result == settings.raw_dir / "srtm_tiles"
        assert result.exists()
        assert result.is_dir()

    @pytest.mark.asyncio
    async def test_logs_warning(self, settings: Settings):
        """Test that warning is logged for unimplemented feature."""
        with patch("projects.stargazer.backend.acquisition.logger") as mock_logger:
            await download_dem(settings)

        mock_logger.warning.assert_called_once()
        assert "not yet implemented" in mock_logger.warning.call_args[0][0].lower()


class TestDownloadIntegration:
    """Integration tests for download functions."""

    @pytest.mark.asyncio
    async def test_all_downloads_use_settings_paths(self, settings: Settings):
        """Test that all downloads use paths from settings."""
        # Pre-create files to skip actual downloads
        settings.raw_dir.mkdir(parents=True, exist_ok=True)
        (settings.raw_dir / "Europe2024.png").touch()
        (settings.raw_dir / "colorbar.png").touch()
        (settings.raw_dir / "scotland-latest.osm.pbf").touch()

        mock_client = AsyncMock()

        lp_result = await download_lp_atlas(settings, mock_client)
        colorbar_result = await download_colorbar(settings, mock_client)
        osm_result = await download_osm_roads(settings, mock_client)
        dem_result = await download_dem(settings)

        # All results should be under raw_dir
        assert lp_result.parent == settings.raw_dir
        assert colorbar_result.parent == settings.raw_dir
        assert osm_result.parent == settings.raw_dir
        assert dem_result.parent == settings.raw_dir
