"""Additional coverage tests for the preprocessing module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from projects.stargazer.backend.config import Settings
from projects.stargazer.backend.preprocessing import (
    extract_roads,
    georeference_raster,
)


class TestGeoreferenceRasterGdalFailure:
    """Tests for georeference_raster propagating CalledProcessError."""

    def test_georeference_raster_gdal_failure(self, settings: Settings):
        """georeference_raster propagates CalledProcessError from gdal_translate."""
        # Create a fake input PNG
        input_png = settings.raw_dir / "Europe2024.png"
        input_png.touch()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1,
                cmd=["gdal_translate"],
                output=b"",
                stderr=b"GDAL error",
            )

            # CalledProcessError should propagate, not be swallowed
            with pytest.raises(subprocess.CalledProcessError):
                georeference_raster(settings)


class TestExtractRoadsAddsMatchingWays:
    """Tests for extract_roads calling writer.add() for matching road Ways."""

    def test_extract_roads_adds_matching_ways(self, settings: Settings):
        """extract_roads calls writer.add() for Ways with matching highway tags."""
        input_pbf = settings.raw_dir / "scotland-latest.osm.pbf"
        input_pbf.touch()

        # Create mock Way objects with matching and non-matching highway tags
        def make_mock_way(highway_tag):
            way = MagicMock()
            way.is_way.return_value = True
            way.tags = {"highway": highway_tag}
            way.tags.get = lambda key, default=None: (
                highway_tag if key == "highway" else default
            )
            return way

        matching_way_primary = make_mock_way("primary")
        matching_way_track = make_mock_way("track")
        non_matching_way_footway = make_mock_way("footway")
        non_matching_way_cycleway = make_mock_way("cycleway")

        fake_objects = [
            matching_way_primary,
            matching_way_track,
            non_matching_way_footway,
            non_matching_way_cycleway,
        ]

        mock_writer_instance = MagicMock()
        mock_writer_instance.__enter__ = MagicMock(return_value=mock_writer_instance)
        mock_writer_instance.__exit__ = MagicMock(return_value=False)

        with patch("osmium.BackReferenceWriter", return_value=mock_writer_instance):
            with patch("osmium.FileProcessor", return_value=fake_objects):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)

                    extract_roads(settings)

        # writer.add should have been called for each matching Way
        assert mock_writer_instance.add.call_count == 2
        mock_writer_instance.add.assert_any_call(matching_way_primary)
        mock_writer_instance.add.assert_any_call(matching_way_track)

        # writer.add should NOT have been called for non-matching Ways
        call_args_list = mock_writer_instance.add.call_args_list
        called_objects = [c[0][0] for c in call_args_list]
        assert non_matching_way_footway not in called_objects
        assert non_matching_way_cycleway not in called_objects

    def test_extract_roads_does_not_add_non_way_objects(self, settings: Settings):
        """extract_roads only calls writer.add() for Way objects, not nodes or relations."""
        input_pbf = settings.raw_dir / "scotland-latest.osm.pbf"
        input_pbf.touch()

        # A node object (is_way returns False)
        node_obj = MagicMock()
        node_obj.is_way.return_value = False
        node_obj.tags = {}
        node_obj.tags.get = lambda key, default=None: default

        mock_writer_instance = MagicMock()
        mock_writer_instance.__enter__ = MagicMock(return_value=mock_writer_instance)
        mock_writer_instance.__exit__ = MagicMock(return_value=False)

        with patch("osmium.BackReferenceWriter", return_value=mock_writer_instance):
            with patch("osmium.FileProcessor", return_value=[node_obj]):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)

                    extract_roads(settings)

        # writer.add should NOT have been called for a non-way object
        mock_writer_instance.add.assert_not_called()
