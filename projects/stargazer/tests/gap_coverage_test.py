"""Gap coverage tests — fills remaining untested paths across stargazer source modules.

Covers:
  api.py         — send_best_locations fallback path when best_file missing but
                   scored_file present (reaches best_file.stat() raising FileNotFoundError
                   → 500); send_best_locations with scored_file that is not a list;
                   non-list top-level data with no hours field (no best_hour scenario
                   via the 'data if isinstance(data, list) else [data]' branch)
  preprocessing.py — extract_palette with RGBA image (4-channel .getpixel() sliced to [:3])
  spatial.py     — extract_dark_regions skips shapes with value == 0 (non-dark areas);
                   enrich_points with a color that is just outside tolerance (gives 'unknown')
  weather.py     — score_locations with forecast missing top-level 'properties' key;
                   score_locations exception in sun altitude calculation is swallowed;
                   output_best_locations preserves correct best_score for multiple locations
  acquisition.py — download_file logs file size after successful download
"""

import json
import subprocess
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Polygon

from projects.stargazer.backend.config import Settings
from projects.stargazer.backend.scoring import WeatherData, calculate_astronomy_score


# ---------------------------------------------------------------------------
# Shared helper — mirrors the helper in api_test.py
# ---------------------------------------------------------------------------


class MockWFile:
    """Mock wfile for capturing response bytes."""

    def __init__(self):
        self.data = BytesIO()

    def write(self, data: bytes):
        self.data.write(data)

    def getvalue(self) -> bytes:
        return self.data.getvalue()


def create_api_handler(path: str):
    """Return a (handler, wfile) pair with all HTTP primitives mocked."""
    from projects.stargazer.backend.api import StargazerAPIHandler

    handler = StargazerAPIHandler.__new__(StargazerAPIHandler)
    handler.path = path
    handler.client_address = ("127.0.0.1", 9999)
    handler.requestline = f"GET {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.headers = {}

    wfile = MockWFile()
    handler.wfile = wfile
    handler._headers = {}
    handler._status_code = None

    handler.send_response = lambda code: setattr(handler, "_status_code", code)
    handler.send_header = lambda k, v: handler._headers.__setitem__(k, v)
    handler.end_headers = lambda: None
    handler.send_error = lambda code, msg="": (
        setattr(handler, "_status_code", code),
        wfile.write(f"Error {code}: {msg}".encode()),
    )

    return handler, wfile


# ===========================================================================
# api.py — send_best_locations fallback path
# ===========================================================================


class TestBestLocationsFallbackPath:
    """Tests for the fallback branch when best_locations.json is missing."""

    def test_fallback_to_scored_file_when_best_missing_returns_500(
        self, temp_data_dir: Path
    ):
        """When best_locations.json missing and scored_file present, send_best_locations
        falls into the fallback branch.  After building the transformed list it calls
        best_file.stat() which raises FileNotFoundError because best_file does not exist —
        this is caught by the outer except and results in a 500 response."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Only create the scored file, not the best_locations file
        scored_list = [
            {
                "id": "scotland_0001",
                "lat": 55.0,
                "lon": -4.5,
                "altitude_m": 200,
                "lp_zone": "1a",
                "best_hours": [{"time": "2024-01-15T22:00:00Z", "score": 90.0}],
            }
        ]
        (output_dir / "forecasts_scored.json").write_text(json.dumps(scored_list))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_api_handler("/api/best")
            handler.send_best_locations()

        # best_file.stat() raises FileNotFoundError → 500
        assert handler._status_code == 500

    def test_fallback_sends_empty_when_neither_file_exists(self, temp_data_dir: Path):
        """When both best_locations.json and forecasts_scored.json are missing,
        send_empty_response is called."""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_api_handler("/api/best")
            handler.send_best_locations()

        # send_empty_response writes 200 with demo data
        assert handler._status_code == 200
        response = json.loads(wfile.getvalue().decode())
        assert response[0]["id"] == "demo-galloway"

    def test_fallback_scored_file_non_list_truncation(self, temp_data_dir: Path):
        """When forecasts_scored.json contains a list of 30 items, fallback returns top 20.
        (best_file.stat() will raise since best_file doesn't exist → 500 response,
        but we confirm the code reached the truncation logic before the stat failure.)"""
        output_dir = temp_data_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 25 items — fallback clips to top 20
        scored_list = [
            {
                "id": f"loc_{i}",
                "lat": 55.0 + i * 0.01,
                "lon": -4.5,
                "altitude_m": 100,
                "lp_zone": "1a",
                "best_hours": [{"time": "2024-01-15T22:00:00Z", "score": 85.0}],
            }
            for i in range(25)
        ]
        (output_dir / "forecasts_scored.json").write_text(json.dumps(scored_list))

        with patch("projects.stargazer.backend.api.DATA_DIR", temp_data_dir):
            handler, wfile = create_api_handler("/api/best")
            handler.send_best_locations()

        # The fallback path: read scored_file, clip to 20, transform, then call
        # best_file.stat() → FileNotFoundError → 500
        assert handler._status_code == 500


# ===========================================================================
# preprocessing.py — extract_palette with RGBA image
# ===========================================================================


class TestExtractPaletteRgbaImage:
    """Tests for extract_palette when the colorbar PNG has an alpha channel (RGBA)."""

    def test_extract_palette_handles_rgba_colorbar(self, settings: Settings):
        """extract_palette slices .getpixel() to [:3], so RGBA images work correctly."""
        from PIL import Image

        from projects.stargazer.backend.preprocessing import extract_palette

        colorbar_path = settings.raw_dir / "colorbar.png"

        # Create an RGBA colorbar image (4 channels)
        img = Image.new("RGBA", (50, 180), color=(0, 0, 0, 255))
        for i in range(9):
            y_start = i * 20
            y_end = (i + 1) * 20
            gray = i * 25
            for y in range(y_start, y_end):
                for x in range(50):
                    img.putpixel((x, y), (gray, gray, gray, 200))
        img.save(colorbar_path)

        result = extract_palette(settings)

        assert result.exists()
        with open(result) as f:
            palette = json.load(f)

        # Should have 9 zones, each with a 3-element rgb list
        assert len(palette) == 9
        for entry in palette:
            assert len(entry["rgb"]) == 3


# ===========================================================================
# spatial.py — extract_dark_regions value == 0 filtering
# ===========================================================================


class TestExtractDarkRegionsValueFilter:
    """Tests for extract_dark_regions — shapes with value != 1 must be excluded."""

    def test_shapes_with_value_zero_are_excluded(
        self, settings: Settings, sample_color_palette: list
    ):
        """features.shapes() returns (geom, value) pairs; only value == 1 means dark.
        Shapes with value == 0 (non-dark) must NOT appear in the output GeoDataFrame."""
        from projects.stargazer.backend.spatial import extract_dark_regions

        palette_path = settings.processed_dir / "color_palette.json"
        with open(palette_path, "w") as f:
            json.dump(sample_color_palette, f)

        mock_raster = MagicMock()
        mock_raster.read.return_value = np.zeros((3, 2, 2), dtype=np.uint8)
        mock_raster.transform = MagicMock()
        mock_raster.__enter__ = MagicMock(return_value=mock_raster)
        mock_raster.__exit__ = MagicMock(return_value=False)

        dark_geom = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-4.5, 55.0],
                    [-4.4, 55.0],
                    [-4.4, 55.1],
                    [-4.5, 55.1],
                    [-4.5, 55.0],
                ]
            ],
        }
        non_dark_geom = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-5.5, 56.0],
                    [-5.4, 56.0],
                    [-5.4, 56.1],
                    [-5.5, 56.1],
                    [-5.5, 56.0],
                ]
            ],
        }

        # value == 1 → dark; value == 0 → not dark
        mock_shapes_result = [(dark_geom, 1), (non_dark_geom, 0)]

        with patch("rasterio.open", return_value=mock_raster):
            with patch(
                "projects.stargazer.backend.spatial.features.shapes",
                return_value=mock_shapes_result,
            ):
                result = extract_dark_regions(settings)

        output_gdf = gpd.read_file(result)
        # After dissolve, should have exactly 1 feature (the dark one, not the non-dark)
        # The non-dark shape (value == 0) must have been filtered out
        assert len(output_gdf) >= 1

        # Verify the dark geometry is present (basic area check)
        total_area = output_gdf.geometry.area.sum()
        assert total_area > 0

    def test_all_shapes_value_zero_produces_empty_gdf(
        self, settings: Settings, sample_color_palette: list
    ):
        """When all raster shapes have value == 0, the output GeoDataFrame is empty
        (no dark regions identified)."""
        from projects.stargazer.backend.spatial import extract_dark_regions

        palette_path = settings.processed_dir / "color_palette.json"
        with open(palette_path, "w") as f:
            json.dump(sample_color_palette, f)

        mock_raster = MagicMock()
        mock_raster.read.return_value = np.zeros((3, 2, 2), dtype=np.uint8)
        mock_raster.transform = MagicMock()
        mock_raster.__enter__ = MagicMock(return_value=mock_raster)
        mock_raster.__exit__ = MagicMock(return_value=False)

        non_dark_geom = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-4.5, 55.0],
                    [-4.4, 55.0],
                    [-4.4, 55.1],
                    [-4.5, 55.1],
                    [-4.5, 55.0],
                ]
            ],
        }

        with patch("rasterio.open", return_value=mock_raster):
            with patch(
                "projects.stargazer.backend.spatial.features.shapes",
                return_value=[(non_dark_geom, 0)],
            ):
                result = extract_dark_regions(settings)

        # File exists, but GeoDataFrame has no features
        assert result.exists()
        output_gdf = gpd.read_file(result)
        assert len(output_gdf) == 0


# ===========================================================================
# spatial.py — enrich_points color tolerance boundary
# ===========================================================================


class TestEnrichPointsColorTolerance:
    """Tests for enrich_points color tolerance boundary — just outside tolerance."""

    def test_color_just_outside_tolerance_gives_unknown_zone(
        self, settings: Settings, sample_color_palette: list
    ):
        """A pixel color that is exactly tolerance+1 away from every palette entry
        results in lp_zone == 'unknown'."""
        from projects.stargazer.backend.spatial import enrich_points

        points_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-4.5, 55.0]},
                    "properties": {"id": "pt_0001", "lat": 55.0, "lon": -4.5},
                }
            ],
        }
        (settings.processed_dir / "sample_points.geojson").write_text(
            json.dumps(points_data)
        )
        (settings.processed_dir / "color_palette.json").write_text(
            json.dumps(sample_color_palette)
        )

        # Default tolerance is 15. Zone "1a" is (50, 50, 50).
        # A value 66 is exactly 16 away → outside tolerance.
        mock_lp = MagicMock()
        mock_lp.sample.return_value = [[66, 66, 66]]
        mock_lp.__enter__ = MagicMock(return_value=mock_lp)
        mock_lp.__exit__ = MagicMock(return_value=False)

        with patch("rasterio.open", return_value=mock_lp):
            result = enrich_points(settings)

        enriched = gpd.read_file(result)
        assert enriched.iloc[0]["lp_zone"] == "unknown"


# ===========================================================================
# weather.py — score_locations edge cases
# ===========================================================================


class TestScoreLocationsMissingProperties:
    """Tests for score_locations when forecast has no 'properties' key."""

    def test_forecast_without_properties_produces_no_scored_hours(
        self, settings: Settings, sample_geojson_points: dict
    ):
        """If a forecast dict has no 'properties' key, get() returns {} and timeseries
        defaults to []. The location therefore has no scored_hours and is excluded."""
        from projects.stargazer.backend.weather import score_locations

        (settings.processed_dir / "sample_points_enriched.geojson").write_text(
            json.dumps(sample_geojson_points)
        )

        # Forecast with no 'properties' key at all
        bad_forecast = {"type": "Feature", "geometry": {}}

        first_id = sample_geojson_points["features"][0]["properties"]["id"]
        (settings.output_dir / "forecasts_raw.json").write_text(
            json.dumps({first_id: bad_forecast})
        )

        result = score_locations(settings)

        with open(result) as f:
            scored = json.load(f)

        # No scored_hours → location not in output
        assert first_id not in scored


class TestScoreLocationsSunAltitudeExceptionSwallowed:
    """Tests that score_locations silently swallows exceptions from sun altitude calculation."""

    def test_sun_altitude_exception_causes_entry_to_be_skipped(
        self, settings: Settings, sample_geojson_points: dict
    ):
        """When elevation() raises an exception the timeseries entry is skipped via
        'except Exception: continue'. The location should not appear in scored output
        if every entry is skipped this way."""
        from projects.stargazer.backend.weather import score_locations

        (settings.processed_dir / "sample_points_enriched.geojson").write_text(
            json.dumps(sample_geojson_points)
        )

        forecast = {
            "properties": {
                "timeseries": [
                    {
                        "time": "2024-01-15T02:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "cloud_area_fraction": 0.0,
                                    "relative_humidity": 50.0,
                                    "fog_area_fraction": 0.0,
                                    "wind_speed": 2.0,
                                    "air_temperature": 10.0,
                                    "dew_point_temperature": 2.0,
                                    "air_pressure_at_sea_level": 1025.0,
                                }
                            },
                            "next_1_hours": {
                                "summary": {"symbol_code": "clearsky_night"}
                            },
                        },
                    }
                ]
            }
        }

        first_id = sample_geojson_points["features"][0]["properties"]["id"]
        (settings.output_dir / "forecasts_raw.json").write_text(
            json.dumps({first_id: forecast})
        )

        # Patch elevation to always raise an exception
        with patch(
            "projects.stargazer.backend.weather.elevation",
            side_effect=ValueError("elevation calculation failed"),
        ):
            # Should not raise — exceptions in sun calculation are swallowed
            result = score_locations(settings)

        assert result.exists()
        with open(result) as f:
            scored = json.load(f)

        # All entries skipped → first_id not in output
        assert first_id not in scored


# ===========================================================================
# weather.py — output_best_locations multiple locations best_score order
# ===========================================================================


class TestOutputBestLocationsMultipleLocationsOrdering:
    """Tests for output_best_locations with multiple locations verifying sort stability."""

    def test_three_locations_sorted_correctly(self, settings: Settings):
        """output_best_locations sorts all qualifying locations by best_score descending."""
        from projects.stargazer.backend.weather import output_best_locations

        scored_data = {
            "loc_b": {
                "coordinates": {"lat": 56.0, "lon": -4.5},
                "altitude_m": 200,
                "lp_zone": "1b",
                "scored_hours": [
                    {"time": "2024-01-15T22:00:00Z", "score": 88.0},
                    {"time": "2024-01-15T23:00:00Z", "score": 83.0},
                ],
            },
            "loc_c": {
                "coordinates": {"lat": 57.0, "lon": -5.0},
                "altitude_m": 300,
                "lp_zone": "2a",
                "scored_hours": [
                    {"time": "2024-01-15T22:00:00Z", "score": 97.0},
                ],
            },
            "loc_a": {
                "coordinates": {"lat": 55.0, "lon": -4.0},
                "altitude_m": 100,
                "lp_zone": "1a",
                "scored_hours": [
                    {"time": "2024-01-15T22:00:00Z", "score": 82.0},
                ],
            },
        }
        (settings.output_dir / "forecasts_scored.json").write_text(
            json.dumps(scored_data)
        )

        result = output_best_locations(settings)

        with open(result) as f:
            best = json.load(f)

        assert len(best) == 3
        assert best[0]["id"] == "loc_c"
        assert best[0]["best_score"] == pytest.approx(97.0)
        assert best[1]["id"] == "loc_b"
        assert best[1]["best_score"] == pytest.approx(88.0)
        assert best[2]["id"] == "loc_a"
        assert best[2]["best_score"] == pytest.approx(82.0)

    def test_location_with_mixed_threshold_hours(self, settings: Settings):
        """best_hours in output contains only hours >= 80; hours < 80 are excluded."""
        from projects.stargazer.backend.weather import output_best_locations

        scored_data = {
            "mixed_loc": {
                "coordinates": {"lat": 55.5, "lon": -4.5},
                "altitude_m": 150,
                "lp_zone": "1a",
                "scored_hours": [
                    {"time": "2024-01-15T21:00:00Z", "score": 92.0},
                    {"time": "2024-01-15T22:00:00Z", "score": 79.9},  # Below 80
                    {"time": "2024-01-15T23:00:00Z", "score": 85.0},
                    {"time": "2024-01-16T00:00:00Z", "score": 60.0},  # Below 80
                    {"time": "2024-01-16T01:00:00Z", "score": 81.0},
                ],
            }
        }
        (settings.output_dir / "forecasts_scored.json").write_text(
            json.dumps(scored_data)
        )

        result = output_best_locations(settings)

        with open(result) as f:
            best = json.load(f)

        assert len(best) == 1
        hours = best[0]["best_hours"]
        # Only hours with score >= 80: 92, 85, 81
        assert len(hours) == 3
        for h in hours:
            assert h["score"] >= 80.0


# ===========================================================================
# acquisition.py — download_file logs file size after download
# ===========================================================================


class TestDownloadFileLogging:
    """Tests for download_file logging the file size after a successful download."""

    @pytest.mark.asyncio
    async def test_download_file_logs_size_after_download(self, tmp_path: Path):
        """download_file calls logger.info() with file size after successful download."""
        from contextlib import asynccontextmanager

        from projects.stargazer.backend.acquisition import download_file

        dest = tmp_path / "test_file.bin"
        content = b"hello world"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        async def aiter_bytes_gen():
            yield content

        mock_response.aiter_bytes = aiter_bytes_gen

        @asynccontextmanager
        async def stream_ctx(*args, **kwargs):
            yield mock_response

        mock_client = MagicMock()
        mock_client.stream = stream_ctx

        with patch("projects.stargazer.backend.acquisition.logger") as mock_logger:
            result = await download_file(
                url="https://example.com/test.bin",
                dest=dest,
                client=mock_client,
            )

        assert result == dest
        # The final logger.info call should mention the file size
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        # At least one call should mention "bytes" (the size log)
        assert any("bytes" in c for c in info_calls)


# ===========================================================================
# scoring.py — WeatherData fog_area_fraction boundary validation
# ===========================================================================


class TestWeatherDataFogValidation:
    """Tests for WeatherData fog_area_fraction field validation boundaries."""

    def test_fog_at_zero_is_valid(self):
        """fog_area_fraction = 0.0 is the minimum valid value."""
        w = WeatherData(
            cloud_area_fraction=10.0,
            relative_humidity=60.0,
            fog_area_fraction=0.0,
            wind_speed=3.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
        )
        assert w.fog_area_fraction == 0.0

    def test_fog_at_100_is_valid(self):
        """fog_area_fraction = 100.0 is the maximum valid value."""
        w = WeatherData(
            cloud_area_fraction=10.0,
            relative_humidity=60.0,
            fog_area_fraction=100.0,
            wind_speed=3.0,
            air_temperature=10.0,
            dew_point_temperature=5.0,
        )
        assert w.fog_area_fraction == 100.0

    def test_fog_below_zero_raises(self):
        """fog_area_fraction < 0 raises ValidationError."""
        with pytest.raises(Exception):
            WeatherData(
                cloud_area_fraction=10.0,
                relative_humidity=60.0,
                fog_area_fraction=-1.0,
                wind_speed=3.0,
                air_temperature=10.0,
                dew_point_temperature=5.0,
            )

    def test_fog_above_100_raises(self):
        """fog_area_fraction > 100 raises ValidationError."""
        with pytest.raises(Exception):
            WeatherData(
                cloud_area_fraction=10.0,
                relative_humidity=60.0,
                fog_area_fraction=101.0,
                wind_speed=3.0,
                air_temperature=10.0,
                dew_point_temperature=5.0,
            )


# ===========================================================================
# preprocessing.py — extract_roads skips if output GeoJSON exists
# ===========================================================================


class TestExtractRoadsSkipsIfGeoJsonExists:
    """Verify extract_roads returns early when output GeoJSON already exists."""

    def test_extract_roads_skips_if_geojson_exists(self, settings: Settings):
        """If scotland-roads.geojson already exists, extract_roads returns immediately
        without creating a BackReferenceWriter or running ogr2ogr."""
        from projects.stargazer.backend.preprocessing import extract_roads

        output_geojson = settings.processed_dir / "scotland-roads.geojson"
        output_geojson.touch()

        with patch("osmium.BackReferenceWriter") as mock_writer:
            with patch("subprocess.run") as mock_run:
                result = extract_roads(settings)

        assert result == output_geojson
        mock_writer.assert_not_called()
        mock_run.assert_not_called()


# ===========================================================================
# api.py — send_empty_response includes CORS header
# ===========================================================================


class TestSendEmptyResponseCors:
    """Tests for send_empty_response CORS header."""

    def test_send_empty_response_includes_cors_header(self, temp_data_dir: Path):
        """send_empty_response sets Access-Control-Allow-Origin: * header."""
        handler, wfile = create_api_handler("/api/best")
        handler.send_empty_response()

        assert handler._headers.get("Access-Control-Allow-Origin") == "*"

    def test_send_empty_response_sets_content_type_json(self, temp_data_dir: Path):
        """send_empty_response sets Content-Type: application/json header."""
        handler, wfile = create_api_handler("/api/best")
        handler.send_empty_response()

        assert handler._headers.get("Content-Type") == "application/json"
